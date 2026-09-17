from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.query.region import (
    NormalizedRegion,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import TimeRangeSpec
from ai_earth_intelligence_and_forecasting_engine.query.statistics import (
    count,
    daily_aggregate,
    filter_observations,
    period_over_period_change,
    regional_aggregate,
    weekly_aggregate,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)


def _obs(
    observation_id: str, when: str, latitude: float, longitude: float
) -> Observation:
    return Observation(
        observation_id=observation_id,
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=datetime.fromisoformat(when).replace(tzinfo=timezone.utc),
        latitude=latitude,
        longitude=longitude,
        source_record_id=observation_id,
        ingested_at=datetime(2024, 8, 21, tzinfo=timezone.utc),
    )


OBSERVATIONS = [
    _obs("1", "2024-08-01T10:00:00", 37.5, -119.5),
    _obs("2", "2024-08-01T14:00:00", 37.6, -119.6),
    _obs("3", "2024-08-01T20:00:00", 37.1, -119.9),
    _obs("4", "2024-08-02T09:00:00", 37.5, -119.5),
    _obs("5", "2024-08-02T15:00:00", 37.5, -119.4),
    _obs("6", "2024-08-08T12:00:00", 37.5, -119.5),
    _obs("7", "2024-08-14T23:00:00", 37.5, -119.5),
    _obs("8", "2024-08-20T10:00:00", 37.5, -119.5),
    _obs("9", "2024-08-01T10:00:00", 37.5, -118.0),
    _obs("10", "2024-07-31T23:00:00", 37.5, -119.5),
]

REGION_1 = NormalizedRegion(
    bbox=(-120.0, 37.0, -119.0, 38.0),
    geometry={"type": "Polygon", "coordinates": []},
    source_kind="bbox",
    label="region_1",
)
REGION_2 = NormalizedRegion(
    bbox=(-118.5, 37.0, -117.5, 38.0),
    geometry={"type": "Polygon", "coordinates": []},
    source_kind="bbox",
    label="region_2",
)

QUERY_WINDOW = normalize_time_range(
    TimeRangeSpec(start="2024-08-01", end="2024-08-14")
)


def test_filter_observations_excludes_outside_region_and_time():
    filtered = filter_observations(OBSERVATIONS, REGION_1, QUERY_WINDOW)

    assert {observation.observation_id for observation in filtered} == {
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
    }


def test_count_matches_hand_verified_total():
    assert count(OBSERVATIONS, REGION_1, QUERY_WINDOW) == 7


def test_count_for_disjoint_region_matches_hand_verified_total():
    assert count(OBSERVATIONS, REGION_2, QUERY_WINDOW) == 1


def test_daily_aggregate_matches_hand_verified_breakdown():
    result = daily_aggregate(OBSERVATIONS, REGION_1, QUERY_WINDOW)

    expected = {
        "2024-08-01": 3,
        "2024-08-02": 2,
        "2024-08-03": 0,
        "2024-08-04": 0,
        "2024-08-05": 0,
        "2024-08-06": 0,
        "2024-08-07": 0,
        "2024-08-08": 1,
        "2024-08-09": 0,
        "2024-08-10": 0,
        "2024-08-11": 0,
        "2024-08-12": 0,
        "2024-08-13": 0,
        "2024-08-14": 1,
    }

    assert {entry.date: entry.count for entry in result} == expected
    assert len(result) == 14
    assert sum(entry.count for entry in result) == 7


def test_weekly_aggregate_matches_hand_verified_breakdown():
    result = weekly_aggregate(OBSERVATIONS, REGION_1, QUERY_WINDOW)

    expected = {
        "2024-07-29": 5,
        "2024-08-05": 1,
        "2024-08-12": 1,
    }

    assert {entry.week_start: entry.count for entry in result} == expected
    assert sum(entry.count for entry in result) == 7


def test_regional_aggregate_matches_hand_verified_totals():
    result = regional_aggregate(OBSERVATIONS, [REGION_1, REGION_2], QUERY_WINDOW)

    assert {entry.label: entry.count for entry in result} == {
        "region_1": 7,
        "region_2": 1,
    }


def test_period_over_period_change_matches_hand_verified_values():
    period_a = normalize_time_range(TimeRangeSpec(start="2024-08-01", end="2024-08-07"))
    period_b = normalize_time_range(TimeRangeSpec(start="2024-08-08", end="2024-08-14"))

    result = period_over_period_change(OBSERVATIONS, REGION_1, period_a, period_b)

    assert result.period_a_count == 5
    assert result.period_b_count == 2
    assert result.absolute_change == -3
    assert result.percent_change == pytest.approx(-60.0)


def test_period_over_period_change_handles_zero_baseline():
    empty_period = normalize_time_range(
        TimeRangeSpec(start="2024-01-01", end="2024-01-07")
    )
    period_a = normalize_time_range(TimeRangeSpec(start="2024-08-01", end="2024-08-07"))

    result = period_over_period_change(OBSERVATIONS, REGION_1, empty_period, period_a)

    assert result.period_a_count == 0
    assert result.period_b_count == 5
    assert result.absolute_change == 5
    assert result.percent_change is None
