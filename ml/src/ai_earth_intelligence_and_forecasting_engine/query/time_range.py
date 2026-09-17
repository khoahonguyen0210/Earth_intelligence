from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from ai_earth_intelligence_and_forecasting_engine.query.schema import TimeRangeSpec


@dataclass(frozen=True)
class NormalizedTimeRange:
    start: datetime  # inclusive
    end: datetime  # exclusive


def _parse_boundary(value: str, *, is_end: bool) -> datetime:
    text = value.strip()

    if not text:
        raise ValueError("time_range boundary must not be empty")

    try:
        parsed_date = date.fromisoformat(text)
    except ValueError:
        parsed_date = None

    if parsed_date is not None:
        boundary = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)

        if is_end:
            boundary += timedelta(days=1)

        return boundary

    try:
        parsed_datetime = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Unparseable time_range boundary: {value!r}") from error

    if parsed_datetime.tzinfo is None:
        parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)
    else:
        parsed_datetime = parsed_datetime.astimezone(timezone.utc)

    return parsed_datetime


def normalize_time_range(time_range: TimeRangeSpec) -> NormalizedTimeRange:
    start = _parse_boundary(time_range.start, is_end=False)
    end = _parse_boundary(time_range.end, is_end=True)

    if start >= end:
        raise ValueError(
            f"time_range start must be before end: "
            f"start={start.isoformat()}, end={end.isoformat()}"
        )

    return NormalizedTimeRange(start=start, end=end)


def contains(time_range: NormalizedTimeRange, timestamp: datetime) -> bool:
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

    normalized_timestamp = timestamp.astimezone(timezone.utc)

    return time_range.start <= normalized_timestamp < time_range.end
