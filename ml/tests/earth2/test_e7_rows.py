from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
    locate_tile,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.earth2.e7 import (
    FORECAST_MODEL,
    NO_FORECAST_MODEL,
    SPLIT_YEARS,
    E7Row,
    build_lead_rows,
    e7_split,
    interpolate_to_cells,
    lead_fire_tiles,
    lead_scores,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)

CUTOFF = datetime(2023, 8, 6, 10, tzinfo=timezone.utc)
LATITUDE, LONGITUDE = 37.55, -119.55
TILE = locate_tile(LATITUDE, LONGITUDE)


def _observation(hours: float, confidence: str = "n") -> Observation:
    return Observation(
        observation_id=f"o{hours}",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=CUTOFF + timedelta(hours=hours),
        latitude=LATITUDE,
        longitude=LONGITUDE,
        source_record_id=str(hours),
        ingested_at=CUTOFF,
        confidence=confidence,
    )


def _row(tile: str, cutoff: datetime, **values) -> DatasetRow:
    fields = dict(
        tile_id=tile,
        cutoff=cutoff,
        split="unassigned",
        target=0,
        previous_24h_count=0,
        previous_72h_count=0,
        previous_7d_count=0,
        previous_30d_count=0,
        neighboring_previous_24h_count=0,
        temperature_2m=300.0,
        total_precipitation=0.0,
        u_wind_10m=1.0,
        v_wind_10m=1.0,
        relative_humidity=30.0,
        elevation_m=500.0,
        slope_deg=5.0,
        land_cover_class=70,
    )
    fields.update(values)
    return DatasetRow(**fields)


def test_split_keeps_the_held_out_test_year_out() -> None:
    years = [year for group in SPLIT_YEARS.values() for year in group]
    assert len(years) == len(set(years))
    assert 2024 not in years
    assert e7_split(CUTOFF.replace(year=2024)) is None
    assert e7_split(CUTOFF.replace(year=2021)) == "train"
    assert e7_split(CUTOFF) == "validation"
    assert e7_split(CUTOFF.replace(year=2025)) == "test"


def test_each_lead_day_counts_only_fires_inside_its_own_day() -> None:
    observations = [
        _observation(0),
        _observation(24),
        _observation(30, confidence="l"),
        _observation(72.5),
    ]
    assert lead_fire_tiles(observations, CUTOFF, 1) == {TILE}
    assert lead_fire_tiles(observations, CUTOFF, 2) == set()
    assert lead_fire_tiles(observations, CUTOFF, 3) == set()
    assert lead_fire_tiles([_observation(48)], CUTOFF, 2) == {TILE}
    assert lead_fire_tiles([_observation(0)], CUTOFF, 1) == set()


def test_interpolation_matches_a_linear_field_on_a_descending_grid() -> None:
    latitude = np.arange(43.0, 31.25, -0.25)
    longitude = np.arange(234.5, 247.25, 0.25)
    field = 2.0 * latitude[:, None] + 0.5 * longitude[None, :]
    cells = build_california_grid()[:500]

    values = interpolate_to_cells(field, latitude, longitude, cells)

    expected = [
        2.0 * cell.centroid_lat + 0.5 * (cell.centroid_lon % 360) for cell in cells
    ]
    assert np.allclose(values, expected)


def test_interpolation_outside_the_forecast_grid_is_missing() -> None:
    latitude = np.array([40.0, 39.0])
    longitude = np.array([240.0, 241.0])
    values = interpolate_to_cells(
        np.ones((2, 2)), latitude, longitude, build_california_grid()[:1]
    )
    assert np.isnan(values[0])


def test_lead_rows_take_targets_splits_and_forecast_values() -> None:
    cutoff_2024 = CUTOFF.replace(year=2024)
    base = [
        _row("a", CUTOFF, target=0),
        _row("b", CUTOFF, target=1),
        _row("a", cutoff_2024),
    ]
    forecasts = {
        CUTOFF: {
            "forecast_hdw_max": np.array([10.0, np.nan]),
            "forecast_wind_max": np.array([5.0, 6.0]),
            "forecast_vpd_max": np.array([2.0, 3.0]),
            "forecast_t2m_max": np.array([300.0, 301.0]),
        }
    }

    rows = build_lead_rows(base, 2, {CUTOFF: {"a"}}, forecasts, {"a": 0, "b": 1})

    assert [(row.tile_id, row.target, row.split) for row in rows] == [
        ("a", 1, "validation"),
        ("b", 0, "validation"),
    ]
    assert rows[0].lead_day == 2
    assert rows[0].forecast_hdw_max == 10.0
    assert rows[1].forecast_hdw_max is None
    assert rows[1].previous_24h_count == 0


def test_lead_scores_fit_both_models_and_keep_the_test_rows_aligned() -> None:
    rng = np.random.default_rng(3)

    def rows_for(year: int, count: int):
        cutoff = CUTOFF.replace(year=year)
        signal = rng.random(count)
        result = []
        for index, value in enumerate(signal):
            fire = int(value > 0.93)
            row = _row(
                f"t{index}",
                cutoff,
                split=e7_split(cutoff),
                target=fire,
                previous_24h_count=int(fire and rng.random() < 0.6),
            )
            fields = dict(row.__dict__)
            fields.update(
                lead_day=1,
                forecast_hdw_max=value * 100,
                forecast_wind_max=value * 10,
                forecast_vpd_max=value * 10,
                forecast_t2m_max=300.0,
            )
            result.append(E7Row(**fields))
        return result

    train = rows_for(2020, 1500)
    validation = rows_for(2023, 600)
    test = rows_for(2025, 400)
    scores, models = lead_scores(train, validation, test, production_model=None)

    assert set(models) == {NO_FORECAST_MODEL, FORECAST_MODEL}
    assert set(scores) == {"climatology", "persistence_24h", *models}
    assert all(len(values) == len(test) for values in scores.values())
    assert all(0 <= value <= 1 for value in scores[FORECAST_MODEL])


@pytest.mark.parametrize("lead", [1, 2, 3])
def test_fire_exactly_at_the_end_of_a_day_belongs_to_that_day(lead: int) -> None:
    observation = _observation(24 * lead)
    assert lead_fire_tiles([observation], CUTOFF, lead) == {TILE}
