from __future__ import annotations

from datetime import datetime, timedelta

STEP_HOURS = 6
LEAD_DAYS = (1, 2, 3)
DAILY_HOURS_UTC = (0, 12, 18)


def initialization_time(cutoff: datetime) -> datetime:
    hour = cutoff.hour - cutoff.hour % STEP_HOURS
    return cutoff.replace(hour=hour, minute=0, second=0, microsecond=0)


def lead_window(cutoff: datetime, lead_day: int) -> tuple[datetime, datetime]:
    return cutoff + timedelta(days=lead_day - 1), cutoff + timedelta(days=lead_day)


def daily_valid_times(cutoff: datetime, lead_day: int) -> list[datetime]:
    start, end = lead_window(cutoff, lead_day)
    time = initialization_time(cutoff)
    times = []
    while time <= end:
        if time > start and time.hour in DAILY_HOURS_UTC:
            times.append(time)
        time += timedelta(hours=STEP_HOURS)
    return times


def forecast_steps(cutoff: datetime) -> int:
    last = daily_valid_times(cutoff, LEAD_DAYS[-1])[-1]
    return (last - initialization_time(cutoff)) // timedelta(hours=STEP_HOURS)
