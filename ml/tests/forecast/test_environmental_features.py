from datetime import datetime, timedelta, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    ERA5Record,
    relative_humidity_percent,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    environmental_features as ef,
)

CUTOFF = datetime(2024, 8, 15, 12, 0, tzinfo=timezone.utc)
TEST_BBOX = (-120.0, 37.0, -119.9, 37.1)  # single cell
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)
TILE = CELLS[0].tile_id


def _era5(
    valid_time: datetime,
    temperature_2m: float = 295.0,
    total_precipitation: float = 0.0,
    u_wind_10m: float = 1.0,
    v_wind_10m: float = -1.0,
    dewpoint_2m: float = 285.0,
    latitude: float = 37.05,
    longitude: float = -119.95,
) -> ERA5Record:
    return ERA5Record(
        latitude=latitude,
        longitude=longitude,
        valid_time=valid_time,
        temperature_2m=temperature_2m,
        total_precipitation=total_precipitation,
        u_wind_10m=u_wind_10m,
        v_wind_10m=v_wind_10m,
        dewpoint_2m=dewpoint_2m,
    )


def _features(era5_records, cells=CELLS, cutoffs=(CUTOFF,), bbox=TEST_BBOX):
    return ef.compute_environmental_features(
        era5_records, cells, list(cutoffs), bbox=bbox
    )


def _only(records):
    assert len(records) == 1
    return records[0]


def test_record_exactly_at_cutoff_is_used():
    record = _era5(CUTOFF, temperature_2m=300.0)

    result = _only(_features([record]))

    assert result.temperature_2m == 300.0
    assert result.era5_valid_time == CUTOFF.isoformat()


def test_uses_most_recent_record_at_or_before_cutoff():
    older = _era5(CUTOFF - timedelta(hours=5), temperature_2m=280.0)
    newer = _era5(CUTOFF - timedelta(hours=1), temperature_2m=295.0)

    result = _only(_features([older, newer]))

    assert result.temperature_2m == 295.0


def test_future_era5_record_does_not_leak_into_past_cutoff():
    past_record = _era5(CUTOFF - timedelta(hours=1), temperature_2m=290.0)
    future_record = _era5(CUTOFF + timedelta(hours=1), temperature_2m=310.0)

    without_future = _features([past_record])
    with_future = _features([past_record, future_record])

    assert without_future == with_future


def test_future_only_record_produces_none_values():
    future_record = _era5(CUTOFF + timedelta(seconds=1))

    result = _only(_features([future_record]))

    assert result.temperature_2m is None
    assert result.era5_valid_time is None


def test_nan_era5_record_treated_as_missing_not_passed_through():
    # ERA5-Land masks ocean cells as NaN; this is "no usable land data",
    # not a real 0/near-zero reading, so it must not leak through as a
    # NaN float.
    ocean_record = _era5(CUTOFF, temperature_2m=float("nan"))

    result = _only(_features([ocean_record]))

    assert result.temperature_2m is None
    assert result.relative_humidity is None
    assert result.era5_valid_time is None


def test_falls_back_to_earlier_usable_record_when_latest_is_nan():
    usable = _era5(CUTOFF - timedelta(hours=2), temperature_2m=290.0)
    ocean_record = _era5(CUTOFF - timedelta(hours=1), temperature_2m=float("nan"))

    result = _only(_features([usable, ocean_record]))

    assert result.temperature_2m == 290.0


def test_missing_era5_data_produces_none_values():
    result = _only(_features([]))

    assert result.temperature_2m is None
    assert result.total_precipitation is None
    assert result.u_wind_10m is None
    assert result.v_wind_10m is None
    assert result.relative_humidity is None


def test_relative_humidity_is_derived_from_temperature_and_dewpoint():
    record = _era5(CUTOFF, temperature_2m=295.0, dewpoint_2m=290.0)

    result = _only(_features([record]))

    expected = relative_humidity_percent(295.0, 290.0)
    assert result.relative_humidity == pytest.approx(expected)


def test_wind_and_precipitation_pass_through_unchanged():
    record = _era5(
        CUTOFF, total_precipitation=0.005, u_wind_10m=2.5, v_wind_10m=-3.5
    )

    result = _only(_features([record]))

    assert result.total_precipitation == 0.005
    assert result.u_wind_10m == 2.5
    assert result.v_wind_10m == -3.5


def test_record_outside_the_cell_does_not_apply():
    record = _era5(CUTOFF, latitude=10.0, longitude=10.0)

    result = _only(_features([record]))

    assert result.temperature_2m is None


def test_compute_environmental_features_one_record_per_cell_per_cutoff():
    bbox = (-120.0, 37.0, -119.8, 37.2)
    cells = build_california_grid(bbox=bbox, resolution_deg=0.1)
    cutoffs = [CUTOFF, CUTOFF + timedelta(hours=1)]

    records = ef.compute_environmental_features([], cells, cutoffs, bbox=bbox)

    assert len(records) == len(cells) * len(cutoffs)
    pairs = {(r.tile_id, r.cutoff) for r in records}
    assert len(pairs) == len(cells) * len(cutoffs)


def test_save_environmental_features_roundtrip(tmp_path):
    record = _era5(CUTOFF)
    records = _features([record])

    output_path = tmp_path / "env_features.csv"
    result = ef.save_environmental_features(records, output_path)

    content = result.read_text(encoding="utf-8")

    assert "temperature_2m" in content
    assert "relative_humidity" in content
    assert TILE in content
