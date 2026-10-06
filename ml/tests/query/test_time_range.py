from datetime import datetime, timedelta, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.query.schema import TimeRangeSpec
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    contains,
    normalize_time_range,
)


def test_date_only_range_normalizes_end_to_start_of_next_day():
    spec = TimeRangeSpec(start="2024-08-08", end="2024-08-15")

    result = normalize_time_range(spec)

    assert result.start == datetime(2024, 8, 8, tzinfo=timezone.utc)
    assert result.end == datetime(2024, 8, 16, tzinfo=timezone.utc)


def test_date_only_range_includes_entire_end_day():
    spec = TimeRangeSpec(start="2024-08-08", end="2024-08-15")
    result = normalize_time_range(spec)

    last_moment_of_end_day = datetime(2024, 8, 15, 23, 59, 59, tzinfo=timezone.utc)
    first_moment_of_next_day = datetime(2024, 8, 16, 0, 0, 0, tzinfo=timezone.utc)

    assert contains(result, last_moment_of_end_day) is True
    assert contains(result, first_moment_of_next_day) is False


def test_date_only_range_includes_start_of_start_day():
    spec = TimeRangeSpec(start="2024-08-08", end="2024-08-15")
    result = normalize_time_range(spec)

    start_of_start_day = datetime(2024, 8, 8, 0, 0, 0, tzinfo=timezone.utc)
    moment_before_start_day = datetime(2024, 8, 7, 23, 59, 59, tzinfo=timezone.utc)

    assert contains(result, start_of_start_day) is True
    assert contains(result, moment_before_start_day) is False


def test_explicit_datetime_end_is_used_exactly_and_excluded():
    spec = TimeRangeSpec(
        start="2024-08-08T00:00:00Z", end="2024-08-15T10:00:00Z"
    )
    result = normalize_time_range(spec)

    exact_end = datetime(2024, 8, 15, 10, 0, 0, tzinfo=timezone.utc)
    one_second_before_end = exact_end - timedelta(seconds=1)

    assert contains(result, exact_end) is False
    assert contains(result, one_second_before_end) is True


def test_explicit_datetime_start_is_used_exactly_and_included():
    spec = TimeRangeSpec(
        start="2024-08-08T06:00:00Z", end="2024-08-15T00:00:00Z"
    )
    result = normalize_time_range(spec)

    exact_start = datetime(2024, 8, 8, 6, 0, 0, tzinfo=timezone.utc)
    one_second_before_start = exact_start - timedelta(seconds=1)

    assert contains(result, exact_start) is True
    assert contains(result, one_second_before_start) is False


def test_normalize_time_range_rejects_start_after_end():
    spec = TimeRangeSpec(start="2024-08-15", end="2024-08-08")

    with pytest.raises(ValueError, match="start must be before end"):
        normalize_time_range(spec)


def test_normalize_time_range_rejects_equal_start_and_end_datetimes():
    spec = TimeRangeSpec(
        start="2024-08-08T10:00:00Z", end="2024-08-08T10:00:00Z"
    )

    with pytest.raises(ValueError, match="start must be before end"):
        normalize_time_range(spec)


def test_normalize_time_range_rejects_empty_boundary():
    spec = TimeRangeSpec(start="", end="2024-08-15")

    with pytest.raises(ValueError, match="must not be empty"):
        normalize_time_range(spec)


def test_normalize_time_range_rejects_unparseable_boundary():
    spec = TimeRangeSpec(start="not-a-date", end="2024-08-15")

    with pytest.raises(ValueError, match="Unparseable"):
        normalize_time_range(spec)


def test_naive_datetime_boundary_is_assumed_utc():
    spec = TimeRangeSpec(start="2024-08-08T00:00:00", end="2024-08-15T00:00:00")
    result = normalize_time_range(spec)

    assert result.start == datetime(2024, 8, 8, tzinfo=timezone.utc)
    assert result.end == datetime(2024, 8, 15, tzinfo=timezone.utc)


def test_non_utc_boundary_is_converted_to_utc():
    spec = TimeRangeSpec(
        start="2024-08-08T00:00:00-05:00", end="2024-08-15T00:00:00-05:00"
    )
    result = normalize_time_range(spec)

    assert result.start == datetime(2024, 8, 8, 5, 0, 0, tzinfo=timezone.utc)


def test_contains_rejects_naive_timestamp():
    spec = TimeRangeSpec(start="2024-08-08", end="2024-08-15")
    result = normalize_time_range(spec)

    with pytest.raises(ValueError, match="timezone-aware"):
        contains(result, datetime(2024, 8, 10))


def test_contains_normalizes_non_utc_timestamp():
    spec = TimeRangeSpec(start="2024-08-08", end="2024-08-15")
    result = normalize_time_range(spec)

    non_utc = datetime(
        2024, 8, 15, 20, 0, 0, tzinfo=timezone(timedelta(hours=-5))
    )

    assert contains(result, non_utc) is False


def test_normalize_time_range_is_deterministic():
    spec = TimeRangeSpec(start="2024-08-08", end="2024-08-15")

    first = normalize_time_range(spec)
    second = normalize_time_range(spec)

    assert first == second
