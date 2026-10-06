from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class QueryIntent(str, Enum):
    COUNT = "count"
    AGGREGATE = "aggregate"
    COMPARE = "compare"
    TREND = "trend"
    MAP = "map"
    FORECAST = "forecast"


@dataclass(frozen=True)
class RegionSpec:
    kind: str
    value: Any


@dataclass(frozen=True)
class TimeRangeSpec:
    start: str
    end: str


@dataclass(frozen=True)
class StructuredEarthQuery:
    question: str
    intent: QueryIntent
    region: RegionSpec
    time_range: TimeRangeSpec
    operation: str


VALID_REGION_KINDS = {"bbox", "coordinates", "named"}


def validate_structured_query(query: StructuredEarthQuery) -> list[str]:
    errors: list[str] = []

    if not query.question.strip():
        errors.append("question must not be empty")

    if not query.operation.strip():
        errors.append("operation must not be empty")

    if query.region.kind not in VALID_REGION_KINDS:
        errors.append(
            f"region.kind must be one of {sorted(VALID_REGION_KINDS)}, "
            f"got: {query.region.kind}"
        )

    if not query.time_range.start.strip():
        errors.append("time_range.start must not be empty")

    if not query.time_range.end.strip():
        errors.append("time_range.end must not be empty")

    return errors
