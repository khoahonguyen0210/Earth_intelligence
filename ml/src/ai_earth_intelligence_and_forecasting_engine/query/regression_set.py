from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    run_analysis,
)

ResultShape = str  # "count" | "daily" | "weekly" | "map"


@dataclass(frozen=True)
class RegressionCase:
    name: str
    payload: dict[str, Any]
    expected_intent: str
    expected_region_kind: str
    expected_region_label: str | None
    expected_operation: str
    expected_result_shape: ResultShape


def _case(
    name: str,
    question: str,
    intent: str,
    region: dict[str, Any],
    start: str,
    end: str,
    operation: str,
    expected_region_label: str | None,
    expected_result_shape: ResultShape,
) -> RegressionCase:
    return RegressionCase(
        name=name,
        payload={
            "question": question,
            "intent": intent,
            "region": region,
            "time_range": {"start": start, "end": end},
            "operation": operation,
        },
        expected_intent=intent,
        expected_region_kind=region["kind"],
        expected_region_label=expected_region_label,
        expected_operation=operation,
        expected_result_shape=expected_result_shape,
    )


REGRESSION_CASES: list[RegressionCase] = [
    _case(
        name="count_named_california",
        question="How many fires occurred in California from Aug 1-20 2024?",
        intent="count",
        region={"kind": "named", "value": "california"},
        start="2024-08-01",
        end="2024-08-20",
        operation="count",
        expected_region_label="california",
        expected_result_shape="count",
    ),
    _case(
        name="count_named_bay_area",
        question="How many fires occurred in the Bay Area from Aug 1-20 2024?",
        intent="count",
        region={"kind": "named", "value": "bay_area"},
        start="2024-08-01",
        end="2024-08-20",
        operation="count",
        expected_region_label="bay_area",
        expected_result_shape="count",
    ),
    _case(
        name="count_named_southern_california",
        question="How many fires occurred in Southern California from Aug 1-20 2024?",
        intent="count",
        region={"kind": "named", "value": "southern_california"},
        start="2024-08-01",
        end="2024-08-20",
        operation="count",
        expected_region_label="southern_california",
        expected_result_shape="count",
    ),
    _case(
        name="count_bbox",
        question="How many fires occurred in this bounding box from Aug 1-20 2024?",
        intent="count",
        region={"kind": "bbox", "value": [-124.5, 32.5, -114.0, 42.0]},
        start="2024-08-01",
        end="2024-08-20",
        operation="count",
        expected_region_label=None,
        expected_result_shape="count",
    ),
    _case(
        name="count_coordinates",
        question="How many fires occurred near this point from Aug 1-20 2024?",
        intent="count",
        region={"kind": "coordinates", "value": [37.8, -122.4]},
        start="2024-08-01",
        end="2024-08-20",
        operation="count",
        expected_region_label="CA_0053_0021",
        expected_result_shape="count",
    ),
    _case(
        name="daily_aggregate_named_california",
        question="Show daily fire counts in California from Aug 1-20 2024",
        intent="aggregate",
        region={"kind": "named", "value": "california"},
        start="2024-08-01",
        end="2024-08-20",
        operation="daily_aggregate",
        expected_region_label="california",
        expected_result_shape="daily",
    ),
    _case(
        name="weekly_aggregate_named_california",
        question="Show weekly fire counts in California from Aug 1-20 2024",
        intent="aggregate",
        region={"kind": "named", "value": "california"},
        start="2024-08-01",
        end="2024-08-20",
        operation="weekly_aggregate",
        expected_region_label="california",
        expected_result_shape="weekly",
    ),
    _case(
        name="map_named_california",
        question="Map fire counts in California from Aug 1-20 2024",
        intent="map",
        region={"kind": "named", "value": "california"},
        start="2024-08-01",
        end="2024-08-20",
        operation="map",
        expected_region_label="california",
        expected_result_shape="map",
    ),
    _case(
        name="map_bbox",
        question="Map fire counts in this bounding box from Aug 1-20 2024",
        intent="map",
        region={"kind": "bbox", "value": [-120.0, 37.0, -119.0, 38.0]},
        start="2024-08-01",
        end="2024-08-20",
        operation="map",
        expected_region_label=None,
        expected_result_shape="map",
    ),
    _case(
        name="count_named_california_single_day",
        question="How many fires occurred in California on Aug 15 2024?",
        intent="count",
        region={"kind": "named", "value": "california"},
        start="2024-08-15",
        end="2024-08-15",
        operation="count",
        expected_region_label="california",
        expected_result_shape="count",
    ),
]


def validate_result_shape(shape: ResultShape, result: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if shape == "count":
        if not isinstance(result.get("count"), int):
            errors.append("expected result.count to be an int")
    elif shape == "daily":
        daily = result.get("daily")
        if not isinstance(daily, list):
            errors.append("expected result.daily to be a list")
        else:
            for entry in daily:
                if "date" not in entry or "count" not in entry:
                    errors.append(f"daily entry missing date/count: {entry!r}")
    elif shape == "weekly":
        weekly = result.get("weekly")
        if not isinstance(weekly, list):
            errors.append("expected result.weekly to be a list")
        else:
            for entry in weekly:
                if "week_start" not in entry or "count" not in entry:
                    errors.append(f"weekly entry missing week_start/count: {entry!r}")
    elif shape == "map":
        if result.get("type") != "FeatureCollection":
            errors.append("expected result.type to be FeatureCollection")
        if not isinstance(result.get("features"), list):
            errors.append("expected result.features to be a list")
    else:
        errors.append(f"unknown expected result shape: {shape!r}")

    return errors


def check_regression_case(
    case: RegressionCase, raw_firms_path: Path
) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []

    response = run_analysis(case.payload, raw_firms_path)
    evidence = response["evidence"]
    result = response["result"]

    if evidence["query_parameters"].get("intent") != case.expected_intent:
        errors.append(
            f"intent mismatch: expected {case.expected_intent!r}, "
            f"got {evidence['query_parameters'].get('intent')!r}"
        )

    if evidence["region_kind"] != case.expected_region_kind:
        errors.append(
            f"region_kind mismatch: expected {case.expected_region_kind!r}, "
            f"got {evidence['region_kind']!r}"
        )

    if evidence["region_label"] != case.expected_region_label:
        errors.append(
            f"region_label mismatch: expected {case.expected_region_label!r}, "
            f"got {evidence['region_label']!r}"
        )

    if evidence["query_parameters"].get("operation") != case.expected_operation:
        errors.append(
            f"operation mismatch: expected {case.expected_operation!r}, "
            f"got {evidence['query_parameters'].get('operation')!r}"
        )

    if not evidence.get("period_start") or not evidence.get("period_end"):
        errors.append("evidence is missing period_start/period_end")

    errors.extend(validate_result_shape(case.expected_result_shape, result))

    return (len(errors) == 0, errors, response)
