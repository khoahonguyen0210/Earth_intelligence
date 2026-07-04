from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation

CATEGORY_SCHEMA = "schema"
CATEGORY_COORDINATES = "coordinates"
CATEGORY_TIMESTAMPS = "timestamps"
CATEGORY_DUPLICATE = "duplicate"
CATEGORY_MISSING_VALUE = "missing_value"
CATEGORY_IMPOSSIBLE_VALUE = "impossible_value"


@dataclass(frozen=True)
class ValidationIssue:
    observation_id: str
    category: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    total_records: int
    valid_records: int
    invalid_records: int
    issues: list[ValidationIssue]
    issues_by_category: dict[str, int]
    generated_at: datetime


def _check_schema(observation: Observation) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    required_string_fields = {
        "observation_id": observation.observation_id,
        "source": observation.source,
        "product": observation.product,
        "source_record_id": observation.source_record_id,
    }

    for field_name, value in required_string_fields.items():
        if not isinstance(value, str) or not value.strip():
            issues.append(
                ValidationIssue(
                    observation_id=observation.observation_id or "<missing>",
                    category=CATEGORY_MISSING_VALUE,
                    message=f"{field_name} is missing or empty",
                )
            )

    if observation.observed_at is None:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id or "<missing>",
                category=CATEGORY_MISSING_VALUE,
                message="observed_at is missing",
            )
        )

    if observation.ingested_at is None:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id or "<missing>",
                category=CATEGORY_MISSING_VALUE,
                message="ingested_at is missing",
            )
        )

    return issues


def _check_coordinates(observation: Observation) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not -90 <= observation.latitude <= 90:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_COORDINATES,
                message=f"latitude out of range: {observation.latitude}",
            )
        )

    if not -180 <= observation.longitude <= 180:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_COORDINATES,
                message=f"longitude out of range: {observation.longitude}",
            )
        )

    if observation.latitude == 0 and observation.longitude == 0:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_IMPOSSIBLE_VALUE,
                message="coordinates are (0, 0), a common sentinel for missing data",
            )
        )

    return issues


def _check_timestamps(observation: Observation) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if observation.observed_at is None or observation.ingested_at is None:
        return issues

    if observation.observed_at.tzinfo is None:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_TIMESTAMPS,
                message="observed_at is not timezone-aware",
            )
        )

    if observation.ingested_at.tzinfo is None:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_TIMESTAMPS,
                message="ingested_at is not timezone-aware",
            )
        )

    if (
        observation.observed_at.tzinfo is not None
        and observation.ingested_at.tzinfo is not None
        and observation.observed_at > observation.ingested_at
    ):
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_TIMESTAMPS,
                message="observed_at is after ingested_at",
            )
        )

    return issues


def _check_impossible_values(observation: Observation) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if observation.quality is not None and not 0 <= observation.quality <= 1:
        issues.append(
            ValidationIssue(
                observation_id=observation.observation_id,
                category=CATEGORY_IMPOSSIBLE_VALUE,
                message=f"quality out of [0, 1] range: {observation.quality}",
            )
        )

    return issues


def validate_observations(observations: list[Observation]) -> ValidationReport:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()
    invalid_record_count = 0

    for observation in observations:
        record_issues: list[ValidationIssue] = []
        record_issues.extend(_check_schema(observation))
        record_issues.extend(_check_coordinates(observation))
        record_issues.extend(_check_timestamps(observation))
        record_issues.extend(_check_impossible_values(observation))

        if observation.observation_id in seen_ids:
            record_issues.append(
                ValidationIssue(
                    observation_id=observation.observation_id,
                    category=CATEGORY_DUPLICATE,
                    message=(
                        f"duplicate observation_id: {observation.observation_id}"
                    ),
                )
            )
        else:
            seen_ids.add(observation.observation_id)

        if record_issues:
            invalid_record_count += 1

        issues.extend(record_issues)

    issues_by_category: dict[str, int] = {}
    for issue in issues:
        issues_by_category[issue.category] = (
            issues_by_category.get(issue.category, 0) + 1
        )

    return ValidationReport(
        total_records=len(observations),
        valid_records=len(observations) - invalid_record_count,
        invalid_records=invalid_record_count,
        issues=issues,
        issues_by_category=issues_by_category,
        generated_at=datetime.now(timezone.utc),
    )


def validation_report_to_dict(report: ValidationReport) -> dict[str, Any]:
    return {
        "total_records": report.total_records,
        "valid_records": report.valid_records,
        "invalid_records": report.invalid_records,
        "issues_by_category": report.issues_by_category,
        "issues": [
            {
                "observation_id": issue.observation_id,
                "category": issue.category,
                "message": issue.message,
            }
            for issue in report.issues
        ],
        "generated_at": report.generated_at.isoformat(),
    }


def save_validation_report(report: ValidationReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(validation_report_to_dict(report), indent=2),
        encoding="utf-8",
    )

    return output_path
