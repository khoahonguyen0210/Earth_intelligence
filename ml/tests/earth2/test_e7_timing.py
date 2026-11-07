from datetime import datetime, timedelta, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.history import (
    historical_cutoffs,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    daily_valid_times,
    forecast_steps,
    initialization_time,
    lead_window,
)

CUTOFF = datetime(2023, 8, 6, 10, tzinfo=timezone.utc)


def _utc(day: int, hour: int) -> datetime:
    return datetime(2023, 8, day, hour, tzinfo=timezone.utc)


@pytest.mark.parametrize("hour", range(24))
def test_initialization_is_never_after_the_cutoff(hour: int) -> None:
    cutoff = CUTOFF.replace(hour=hour, minute=30)
    start = initialization_time(cutoff)
    assert start <= cutoff
    assert cutoff - start < timedelta(hours=6)
    assert start.hour % 6 == 0


def test_every_e7_cutoff_starts_from_an_earlier_analysis() -> None:
    for cutoff in historical_cutoffs(2019, 2025):
        assert initialization_time(cutoff) == cutoff.replace(hour=6)


def test_lead_days_use_the_papers_daily_hours_inside_their_window() -> None:
    assert daily_valid_times(CUTOFF, 1) == [_utc(6, 12), _utc(6, 18), _utc(7, 0)]
    assert daily_valid_times(CUTOFF, 2) == [_utc(7, 12), _utc(7, 18), _utc(8, 0)]
    assert daily_valid_times(CUTOFF, 3) == [_utc(8, 12), _utc(8, 18), _utc(9, 0)]


def test_forecast_times_come_after_the_cutoff_and_inside_the_lead_window() -> None:
    for lead in LEAD_DAYS:
        start, end = lead_window(CUTOFF, lead)
        for time in daily_valid_times(CUTOFF, lead):
            assert CUTOFF <= start < time <= end


def test_three_days_need_eleven_six_hour_steps() -> None:
    assert forecast_steps(CUTOFF) == 11
