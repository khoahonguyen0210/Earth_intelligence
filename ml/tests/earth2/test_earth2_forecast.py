from __future__ import annotations

from collections import OrderedDict

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (  # noqa: E402
    INDEX_LEVELS_HPA,
    build_columns,
    crop_indices,
    daily_features,
    dewpoint_from_vapor_pressure,
    lowest_level_above_ground,
    required_variables,
    select_fields,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (  # noqa: E402
    compute_index,
    saturation_vapor_pressure,
    vapor_pressure,
)


def _fields(shape=(2, 3), seed=0) -> dict[str, torch.Tensor]:
    generator = torch.Generator().manual_seed(seed)

    def uniform(low: float, high: float) -> torch.Tensor:
        return low + (high - low) * torch.rand(
            shape, generator=generator, dtype=torch.float64
        )

    fields = {
        "t2m": uniform(285.0, 310.0),
        "u10m": uniform(-8.0, 8.0),
        "v10m": uniform(-8.0, 8.0),
        "sp": uniform(80000.0, 101000.0),
    }
    for level in INDEX_LEVELS_HPA:
        fields[f"t{level}"] = uniform(260.0, 300.0)
        fields[f"q{level}"] = uniform(1e-3, 1e-2)
        fields[f"u{level}"] = uniform(-15.0, 15.0)
        fields[f"v{level}"] = uniform(-15.0, 15.0)
    return fields


def test_dewpoint_inverts_the_saturation_formula() -> None:
    kelvin = torch.tensor([250.0, 273.15, 300.0, 320.0], dtype=torch.float64)
    recovered = dewpoint_from_vapor_pressure(saturation_vapor_pressure(kelvin))
    assert torch.allclose(recovered, kelvin)


def test_lowest_level_above_ground_skips_levels_below_the_surface() -> None:
    pressure = torch.tensor([1000.0, 925.0, 850.0])
    values = torch.tensor([1.0, 2.0, 3.0]).view(3, 1, 1).expand(3, 1, 2)
    surface = torch.tensor([[1010.0, 900.0]])
    assert lowest_level_above_ground(values, pressure, surface).tolist() == [[1.0, 3.0]]


def test_missing_model_variables_are_reported() -> None:
    fields = _fields()
    del fields["sp"]
    with pytest.raises(ValueError, match="sp"):
        build_columns(fields)


def test_columns_use_model_dew_point_when_present() -> None:
    fields = _fields()
    fields["d2m"] = fields["t2m"] - 10.0
    columns, approximate = build_columns(fields)
    assert not approximate
    assert torch.equal(columns.d2m, fields["d2m"])
    assert columns.temperature.shape == (len(INDEX_LEVELS_HPA), 2, 3)


def test_columns_without_dew_point_use_the_lowest_level_humidity() -> None:
    fields = _fields()
    columns, approximate = build_columns(fields)
    surface = fields["sp"] / 100.0
    pressure = torch.tensor(INDEX_LEVELS_HPA, dtype=torch.float64)
    humidity = torch.stack([fields[f"q{level}"] for level in INDEX_LEVELS_HPA])
    lowest = lowest_level_above_ground(humidity, pressure, surface)

    assert approximate
    assert torch.allclose(
        saturation_vapor_pressure(columns.d2m), vapor_pressure(lowest, surface)
    )


def test_daily_features_take_the_highest_value_of_the_day() -> None:
    first, _ = build_columns(_fields(seed=1))
    second, _ = build_columns(_fields(seed=2))

    features = daily_features([first, second])

    expected = torch.maximum(compute_index(first), compute_index(second))
    assert torch.allclose(features["hdw_max"], expected)
    assert torch.equal(features["t2m_max"], torch.maximum(first.t2m, second.t2m))


def test_missing_surface_pressure_gives_a_missing_index() -> None:
    fields = _fields()
    fields["sp"][0, 0] = float("nan")
    columns, _ = build_columns(fields)
    features = daily_features([columns])
    assert torch.isnan(features["hdw_max"][0, 0])
    assert not torch.isnan(features["hdw_max"][1, 1])


def test_crop_covers_california_on_the_global_quarter_degree_grid() -> None:
    latitude = np.linspace(90.0, -90.0, 721)
    longitude = np.arange(0.0, 360.0, 0.25)
    rows, columns = crop_indices(latitude, longitude)
    assert latitude[rows].min() <= 32.5 and latitude[rows].max() >= 42.0
    assert longitude[columns].min() <= 235.5 and longitude[columns].max() >= 246.0


def test_select_fields_reads_the_last_step_and_the_crop() -> None:
    variables = np.array(required_variables())
    output = torch.arange(1 * 1 * len(variables) * 4 * 5, dtype=torch.float64)
    output = output.view(1, 1, len(variables), 4, 5)
    coords = OrderedDict(
        time=np.array([0]),
        lead_time=np.array([6]),
        variable=variables,
        lat=np.arange(4.0),
        lon=np.arange(5.0),
    )
    rows, columns = np.array([1, 2]), np.array([0, 3])

    fields = select_fields(output, coords, ["sp", "q700", "d2m"], rows, columns)

    assert set(fields) == {"sp", "q700"}
    position = list(variables).index("sp")
    assert torch.equal(fields["sp"], output[0, 0, position][[1, 2]][:, [0, 3]])
