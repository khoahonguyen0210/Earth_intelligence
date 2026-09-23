from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    load_firms_history,
    require_firms_coverage,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.query.evidence import (
    build_evidence_from_query,
    evidence_to_dict,
)
from ai_earth_intelligence_and_forecasting_engine.query.map_result import (
    build_regional_map_result,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    QueryIntent,
    RegionSpec,
    StructuredEarthQuery,
    TimeRangeSpec,
    validate_structured_query,
)
from ai_earth_intelligence_and_forecasting_engine.query.statistics import (
    count,
    daily_aggregate,
    weekly_aggregate,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)

DATASET_LABEL = "NASA_FIRMS:VIIRS_SNPP_SP"

SUPPORTED_OPERATIONS = {"count", "daily_aggregate", "weekly_aggregate", "map"}


def parse_request(payload: dict[str, Any]) -> StructuredEarthQuery:
    region_payload = payload["region"]
    time_range_payload = payload["time_range"]

    return StructuredEarthQuery(
        question=payload["question"],
        intent=QueryIntent(payload["intent"]),
        region=RegionSpec(kind=region_payload["kind"], value=region_payload["value"]),
        time_range=TimeRangeSpec(
            start=time_range_payload["start"], end=time_range_payload["end"]
        ),
        operation=payload["operation"],
    )


def load_firms_observations(raw_path: Path) -> list[Observation]:
    config = load_firms_config()
    csv_text = raw_path.read_text(encoding="utf-8")
    records = parse_firms_records(csv_text)

    ingested_at = datetime.now(timezone.utc)

    return [
        normalize_firms_record(
            record=record,
            product=config.product,
            source_record_id=str(index),
            ingested_at=ingested_at,
        )
        for index, record in enumerate(records)
    ]


def load_observations_for(
    raw_firms_path: Path, start: datetime, end: datetime
) -> list[Observation]:
    """`raw_firms_path` is either one FIRMS CSV or the fire-season
    history directory. For the history, the requested period must be
    fully covered, and a day of margin either side is loaded; the
    statistics apply the exact time range themselves."""
    if not raw_firms_path.is_dir():
        return load_firms_observations(raw_firms_path)

    last_instant = end - timedelta(
        microseconds=1
    )  # NormalizedTimeRange.end is exclusive
    require_firms_coverage(
        raw_firms_path,
        start,
        last_instant,
        f"{start.date().isoformat()} to {last_instant.date().isoformat()}",
    )
    return load_firms_history(
        raw_firms_path, start - timedelta(days=1), end + timedelta(days=1)
    )


def run_analysis(payload: dict[str, Any], raw_firms_path: Path) -> dict[str, Any]:
    query = parse_request(payload)

    errors = validate_structured_query(query)

    if query.operation not in SUPPORTED_OPERATIONS:
        errors.append(
            f"Unsupported operation: {query.operation!r}. "
            f"Supported: {sorted(SUPPORTED_OPERATIONS)}"
        )

    if errors:
        raise ValueError("; ".join(errors))

    region = normalize_region(query.region)
    time_range = normalize_time_range(query.time_range)
    observations = load_observations_for(
        raw_firms_path, time_range.start, time_range.end
    )

    result: dict[str, Any]

    if query.operation == "count":
        result = {"count": count(observations, region, time_range)}
    elif query.operation == "daily_aggregate":
        result = {
            "daily": [
                {"date": entry.date, "count": entry.count}
                for entry in daily_aggregate(observations, region, time_range)
            ]
        }
    elif query.operation == "weekly_aggregate":
        result = {
            "weekly": [
                {"week_start": entry.week_start, "count": entry.count}
                for entry in weekly_aggregate(observations, region, time_range)
            ]
        }
    else:  # operation == "map"
        result = build_regional_map_result(observations, [region], time_range)

    evidence = build_evidence_from_query(
        query=query, dataset=DATASET_LABEL, region=region, time_range=time_range
    )

    return {"result": result, "evidence": evidence_to_dict(evidence)}
