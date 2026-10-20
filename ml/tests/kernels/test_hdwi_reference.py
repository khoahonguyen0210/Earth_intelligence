from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (  # noqa: E402
    relative_humidity_percent,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.fixtures import (  # noqa: E402
    DENSE_LEVELS,
    EDGE_CASES,
    FCN3_LEVELS,
    edge_case_columns,
    random_columns,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (  # noqa: E402
    KAPPA,
    ColumnFields,
    hot_dry_windy_index,
    layer_mask,
    saturation_vapor_pressure,
    surface_hot_dry_windy_index,
    surface_vpd,
    surface_vpd_from_relative_humidity,
)


def _es(kelvin: float) -> float:
    celsius = kelvin - 273.15
    return 6.1094 * math.exp(17.625 * celsius / (243.04 + celsius))


def _single_column(
    surface_hpa: float, levels: tuple[int, ...], **overrides: list[float]
) -> ColumnFields:
    count = len(levels)
    base = {
        "temperature": [300.0 - 0.07 * (1000 - level) for level in levels],
        "specific_humidity": [0.006] * count,
        "u": [4.0] * count,
        "v": [3.0] * count,
    }
    base.update(overrides)

    def surface(value: float) -> torch.Tensor:
        return torch.tensor([[value]], dtype=torch.float64)

    def stacked(values: list[float]) -> torch.Tensor:
        return torch.tensor(values, dtype=torch.float64).view(-1, 1, 1)

    return ColumnFields(
        t2m=surface(303.15),
        d2m=surface(283.15),
        u10=surface(3.0),
        v10=surface(4.0),
        surface_pressure=surface(surface_hpa * 100.0),
        temperature=stacked(base["temperature"]),
        specific_humidity=stacked(base["specific_humidity"]),
        u=stacked(base["u"]),
        v=stacked(base["v"]),
        pressure=torch.tensor(levels, dtype=torch.float64),
    )


def test_vapor_pressure_deficit_matches_paper_examples() -> None:
    cold = 0.8 * saturation_vapor_pressure(torch.tensor(273.15, dtype=torch.float64))
    warm = 0.8 * saturation_vapor_pressure(torch.tensor(303.15, dtype=torch.float64))
    assert float(cold) == pytest.approx(4.9, abs=0.15)
    assert float(warm) == pytest.approx(34.0, abs=0.15)


@pytest.mark.parametrize(
    ("surface_hpa", "levels", "expected"),
    [
        (1000.0, (1000, 975, 950, 925, 900), [1, 1, 1, 1, 0]),
        (960.0, (1000, 975, 950, 925, 900), [0, 0, 1, 1, 1]),
        (1013.0, FCN3_LEVELS[:4], [1, 1, 0, 0]),
        (915.0, FCN3_LEVELS[:4], [0, 0, 1, 0]),
        (705.0, DENSE_LEVELS, [0] * 11 + [1]),
    ],
)
def test_layer_holds_levels_up_to_first_beyond_50_hpa(
    surface_hpa: float, levels: tuple[int, ...], expected: list[int]
) -> None:
    mask = layer_mask(
        torch.tensor(levels, dtype=torch.float64),
        torch.tensor([[surface_hpa]], dtype=torch.float64),
    )
    assert mask.view(-1).int().tolist() == expected


def test_index_matches_hand_calculation() -> None:
    levels = (1000, 975, 950, 925, 900)
    columns = _single_column(1000.0, levels)
    result = float(hot_dry_windy_index(columns))

    winds = [5.0] + [5.0] * 4
    vpds = [_es(303.15) - _es(283.15)]
    for level, temperature in zip(levels[:4], columns.temperature.view(-1)[:4]):
        lowered = float(temperature) * (1000.0 / level) ** KAPPA
        vapor = 0.006 * 1000.0 / (0.622 + 0.378 * 0.006)
        vpds.append(max(_es(lowered) - vapor, 0.0))

    assert result == pytest.approx(max(winds) * max(vpds), rel=1e-12)


def test_levels_outside_the_layer_are_ignored() -> None:
    levels = (1000, 975, 950, 925, 900, 850)
    calm = _single_column(1000.0, levels)
    stormy = _single_column(
        1000.0, levels, u=[4.0, 4.0, 4.0, 4.0, 90.0, 90.0], v=[3.0] * 6
    )
    assert float(hot_dry_windy_index(stormy)) == float(hot_dry_windy_index(calm))

    used = _single_column(
        1000.0, levels, u=[4.0, 4.0, 4.0, 30.0, 90.0, 90.0], v=[3.0] * 6
    )
    assert float(hot_dry_windy_index(used)) > float(hot_dry_windy_index(calm))


def test_edge_cases() -> None:
    result = hot_dry_windy_index(edge_case_columns()).view(-1)
    outcome = dict(zip(EDGE_CASES, result.tolist()))

    for name in ("nan_surface", "nan_used_level", "nan_surface_pressure"):
        assert math.isnan(outcome[name])
    for name in ("typical", "nan_below_ground", "nan_above_layer", "high_terrain"):
        assert math.isfinite(outcome[name]) and outcome[name] > 0
    assert outcome["calm_wind"] == 0.0
    assert outcome["extreme_values"] > outcome["typical"]


def test_saturated_air_has_no_surface_deficit() -> None:
    columns = edge_case_columns()
    case = EDGE_CASES.index("saturated_surface")
    deficit = surface_vpd(columns.t2m, columns.d2m).view(-1)[case]
    assert float(deficit) == 0.0


def test_leading_dimensions_are_kept() -> None:
    columns = random_columns((2, 3), 4, 5, seed=1, dtype=torch.float64)
    assert hot_dry_windy_index(columns).shape == (2, 3, 4, 5)


def test_float32_matches_float64() -> None:
    columns = random_columns((2,), 16, 32, seed=2, dtype=torch.float64)
    exact = hot_dry_windy_index(columns)
    single = hot_dry_windy_index(columns.to("cpu", torch.float32))
    torch.testing.assert_close(single.double(), exact, rtol=1e-4, atol=1e-3)


def test_rejects_ascending_levels() -> None:
    columns = random_columns((), 2, 2, seed=3, dtype=torch.float64)
    flipped = ColumnFields(
        **{
            name: getattr(columns, name)
            for name in ("t2m", "d2m", "u10", "v10", "surface_pressure")
        },
        temperature=columns.temperature.flip(-3),
        specific_humidity=columns.specific_humidity.flip(-3),
        u=columns.u.flip(-3),
        v=columns.v.flip(-3),
        pressure=columns.pressure.flip(0),
    )
    with pytest.raises(ValueError, match="descending"):
        hot_dry_windy_index(flipped)


def test_rejects_mismatched_shapes() -> None:
    columns = random_columns((), 2, 2, seed=4, dtype=torch.float64)
    broken = ColumnFields(
        **{
            name: getattr(columns, name)
            for name in ("t2m", "d2m", "u10", "v10", "surface_pressure")
        },
        temperature=columns.temperature[:-1],
        specific_humidity=columns.specific_humidity,
        u=columns.u,
        v=columns.v,
        pressure=columns.pressure,
    )
    with pytest.raises(ValueError, match="temperature"):
        hot_dry_windy_index(broken)


def test_surface_index_agrees_with_dataset_humidity() -> None:
    t2m = torch.tensor([[300.0, 310.0]], dtype=torch.float64)
    d2m = torch.tensor([[285.0, 280.0]], dtype=torch.float64)
    humidity = torch.tensor(
        [
            [
                relative_humidity_percent(300.0, 285.0),
                relative_humidity_percent(310.0, 280.0),
            ]
        ],
        dtype=torch.float64,
    )
    torch.testing.assert_close(
        surface_vpd_from_relative_humidity(t2m, humidity), surface_vpd(t2m, d2m)
    )

    u10 = torch.tensor([[3.0, 0.0]], dtype=torch.float64)
    v10 = torch.tensor([[4.0, 4.0]], dtype=torch.float64)
    expected = torch.tensor([[5.0, 4.0]], dtype=torch.float64) * surface_vpd(t2m, d2m)
    torch.testing.assert_close(
        surface_hot_dry_windy_index(t2m, d2m, u10, v10), expected
    )
