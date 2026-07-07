from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, timezone

from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.query.region import NormalizedRegion
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    NormalizedTimeRange,
    contains,
)


@dataclass(frozen=True)
class DailyCount:
    date: str
    count: int


@dataclass(frozen=True)
class WeeklyCount:
    week_start: str
    count: int


@dataclass(frozen=True)
class RegionalCount:
    label: str
    count: int


@dataclass(frozen=True)
class PeriodChange:
    period_a_count: int
    period_b_count: int
    absolute_change: int
    percent_change: float | None


def _region_contains_point(
    region: NormalizedRegion, latitude: float, longitude: float
) -> bool:
    west, south, east, north = region.bbox

    return west <= longitude < east and south <= latitude < north


def filter_observations(
    observations: list[Observation],
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
) -> list[Observation]:
    return [
        observation
        for observation in observations
        if _region_contains_point(
            region, observation.latitude, observation.longitude
        )
        and contains(time_range, observation.observed_at)
    ]


def count(
    observations: list[Observation],
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
) -> int:
    return len(filter_observations(observations, region, time_range))


def _bucket_dates(time_range: NormalizedTimeRange) -> list[date]:
    if time_range.start >= time_range.end:
        return []

    # end is exclusive; the last instant actually included in the range is
    # one microsecond before it, which correctly handles both a midnight
    # end (excludes that calendar day) and a partial-day end (includes it).
    last_included_instant = time_range.end - timedelta(microseconds=1)

    start_date = time_range.start.date()
    end_date = last_included_instant.date()

    dates: list[date] = []
    current = start_date

    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)

    return dates


def daily_aggregate(
    observations: list[Observation],
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
) -> list[DailyCount]:
    filtered = filter_observations(observations, region, time_range)

    counts: dict[date, int] = dict.fromkeys(_bucket_dates(time_range), 0)

    for observation in filtered:
        day = observation.observed_at.astimezone(timezone.utc).date()

        if day in counts:
            counts[day] += 1

    return [
        DailyCount(date=day.isoformat(), count=counts[day]) for day in sorted(counts)
    ]


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weekly_aggregate(
    observations: list[Observation],
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
) -> list[WeeklyCount]:
    filtered = filter_observations(observations, region, time_range)

    bucket_days = _bucket_dates(time_range)
    week_starts = sorted({_week_start(day) for day in bucket_days})
    counts: dict[date, int] = dict.fromkeys(week_starts, 0)

    for observation in filtered:
        day = observation.observed_at.astimezone(timezone.utc).date()
        week_start = _week_start(day)

        if week_start in counts:
            counts[week_start] += 1

    return [
        WeeklyCount(week_start=week.isoformat(), count=counts[week])
        for week in sorted(counts)
    ]


def regional_aggregate(
    observations: list[Observation],
    regions: list[NormalizedRegion],
    time_range: NormalizedTimeRange,
) -> list[RegionalCount]:
    return [
        RegionalCount(
            label=region.label or region.source_kind,
            count=count(observations, region, time_range),
        )
        for region in regions
    ]


def period_over_period_change(
    observations: list[Observation],
    region: NormalizedRegion,
    period_a: NormalizedTimeRange,
    period_b: NormalizedTimeRange,
) -> PeriodChange:
    count_a = count(observations, region, period_a)
    count_b = count(observations, region, period_b)

    absolute_change = count_b - count_a
    percent_change = (absolute_change / count_a * 100) if count_a != 0 else None

    return PeriodChange(
        period_a_count=count_a,
        period_b_count=count_b,
        absolute_change=absolute_change,
        percent_change=percent_change,
    )
