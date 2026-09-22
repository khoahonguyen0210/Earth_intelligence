from datetime import datetime, timedelta, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.live import check_live_cutoff
from ai_earth_intelligence_and_forecasting_engine.data.outlook import (
    check_outlook_cutoff,
    record_from_hourly,
    wind_components,
)

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


def test_recent_cutoff_is_accepted():
    check_live_cutoff(NOW - timedelta(days=3), NOW)


def test_stale_cutoff_is_rejected():
    with pytest.raises(ValueError, match="older than the live data window"):
        check_live_cutoff(NOW - timedelta(days=200), NOW)


def test_cutoff_beyond_outlook_range_is_rejected():
    with pytest.raises(ValueError, match="at most 7 days"):
        check_outlook_cutoff(datetime(2027, 6, 16, tzinfo=timezone.utc), NOW)


def test_cutoff_within_outlook_range_is_accepted():
    check_outlook_cutoff(NOW + timedelta(days=5), NOW)


def test_wind_from_the_west_blows_east():
    u_wind, v_wind = wind_components(10.0, 270.0)
    assert u_wind == pytest.approx(10.0)
    assert v_wind == pytest.approx(0.0, abs=1e-9)


def test_record_converts_to_era5_units():
    hourly = {
        "temperature_2m": [20.0, 25.0],
        "dew_point_2m": [10.0, 5.0],
        "precipitation": [1.0, 2.0],
        "wind_speed_10m": [3.0, 4.0],
        "wind_direction_10m": [0.0, 180.0],
    }
    record = record_from_hourly(hourly, 1, 37.0, -120.0, NOW)
    assert record.temperature_2m == pytest.approx(298.15)
    assert record.dewpoint_2m == pytest.approx(278.15)
    assert record.total_precipitation == pytest.approx(0.003)
    assert record.v_wind_10m == pytest.approx(4.0)
