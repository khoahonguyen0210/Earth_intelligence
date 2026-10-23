from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (  # noqa: E402
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.research.fire_weather import (  # noqa: E402
    complete_weather,
    local_percentile,
    surface_index_components,
)

CUTOFF = datetime(2023, 8, 1, 10, tzinfo=timezone.utc)


def _row(temperature: float | None, humidity: float, u: float, v: float) -> DatasetRow:
    return DatasetRow(
        tile_id="CA_0001_0002",
        cutoff=CUTOFF,
        split="validation",
        target=0,
        previous_24h_count=0,
        previous_72h_count=0,
        previous_7d_count=0,
        previous_30d_count=0,
        neighboring_previous_24h_count=0,
        temperature_2m=temperature,
        total_precipitation=0.0,
        u_wind_10m=u,
        v_wind_10m=v,
        relative_humidity=humidity,
        elevation_m=100.0,
        slope_deg=1.0,
        land_cover_class=7,
    )


def test_components_follow_the_surface_formula() -> None:
    components = surface_index_components([_row(303.15, 20.0, 3.0, 4.0)])
    celsius = 30.0
    saturation = 6.1094 * math.exp(17.625 * celsius / (243.04 + celsius))

    assert components["wind_speed_10m"][0] == pytest.approx(5.0)
    assert components["surface_vpd"][0] == pytest.approx(0.8 * saturation)
    assert components["surface_hdw"][0] == pytest.approx(5.0 * 0.8 * saturation)


def test_rows_without_weather_are_flagged() -> None:
    rows = [_row(300.0, 40.0, 1.0, 1.0), _row(None, 40.0, 1.0, 1.0)]
    keep = complete_weather(surface_index_components(rows))
    assert keep.tolist() == [True, False]


def test_local_percentile_ranks_against_the_same_cell() -> None:
    reference_tiles = ["a", "a", "a", "a", "b", "b"]
    reference_values = np.array([1.0, 2.0, 3.0, 4.0, 100.0, 200.0])
    result = local_percentile(
        reference_tiles,
        reference_values,
        ["a", "b", "a", "c"],
        np.array([3.5, 150.0, np.nan, 1.0]),
    )
    assert result[0] == pytest.approx(0.75)
    assert result[1] == pytest.approx(0.5)
    assert np.isnan(result[2]) and np.isnan(result[3])


def test_humid_air_has_no_deficit() -> None:
    components = surface_index_components([_row(290.0, 104.0, 2.0, 0.0)])
    assert components["surface_hdw"][0] == 0.0
    assert np.isfinite(components["surface_hdw"]).all()
