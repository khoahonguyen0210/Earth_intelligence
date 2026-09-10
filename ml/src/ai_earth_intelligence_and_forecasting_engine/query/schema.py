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
    """Raw, unresolved region input.

    `kind` is one of "bbox", "coordinates", or "named". The shape of
    `value` depends on `kind`:
      - "bbox": (west, south, east, north)
      - "coordinates": (latitude, longitude)
      - "named": the region name, e.g. "California"

    normalize_region resolves this into deterministic geometry; this
    type only carries what the query stated, unresolved.
    """

    kind: str
    value: Any


@dataclass(frozen=True)
class TimeRangeSpec:
    """Raw, unresolved time range input.

    `start`/`end` are ISO 8601 date or datetime strings as stated in the
    query. normalize_time_range implements the exact inclusive/exclusive
    boundary semantics; this type only carries what the query stated.
    """

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
