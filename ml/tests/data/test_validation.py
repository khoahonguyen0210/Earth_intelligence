import json
from datetime import datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.data.validation import (
    CATEGORY_COORDINATES,
    CATEGORY_DUPLICATE,
    CATEGORY_IMPOSSIBLE_VALUE,
    CATEGORY_MISSING_VALUE,
    CATEGORY_TIMESTAMPS,
    save_validation_report,
    validate_observations,
    validation_report_to_dict,
)

OBSERVED_AT = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)
INGESTED_AT = datetime(2024, 8, 15, 12, 0, tzinfo=timezone.utc)


def _valid_observation(observation_id: str = "firms:001") -> Observation:
    return Observation(
        observation_id=observation_id,
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=OBSERVED_AT,
        latitude=37.5,
        longitude=-119.5,
        source_record_id="001",
        ingested_at=INGESTED_AT,
        quality=0.8,
        confidence="n",
    )


def test_valid_observation_produces_no_issues():
    report = validate_observations([_valid_observation()])

    assert report.total_records == 1
    assert report.valid_records == 1
    assert report.invalid_records == 0
    assert report.issues == []


def test_missing_observation_id_flagged():
    observation = _valid_observation(observation_id="")

    report = validate_observations([observation])

    assert report.invalid_records == 1
    assert any(issue.category == CATEGORY_MISSING_VALUE for issue in report.issues)


def test_invalid_latitude_flagged():
    observation = Observation(
        observation_id="firms:002",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=OBSERVED_AT,
        latitude=91.0,
        longitude=-119.5,
        source_record_id="002",
        ingested_at=INGESTED_AT,
    )

    report = validate_observations([observation])

    assert report.invalid_records == 1
    assert any(issue.category == CATEGORY_COORDINATES for issue in report.issues)


def test_invalid_longitude_flagged():
    observation = Observation(
        observation_id="firms:003",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=OBSERVED_AT,
        latitude=37.5,
        longitude=-200.0,
        source_record_id="003",
        ingested_at=INGESTED_AT,
    )

    report = validate_observations([observation])

    assert any(issue.category == CATEGORY_COORDINATES for issue in report.issues)


def test_null_island_flagged_as_impossible():
    observation = Observation(
        observation_id="firms:004",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=OBSERVED_AT,
        latitude=0.0,
        longitude=0.0,
        source_record_id="004",
        ingested_at=INGESTED_AT,
    )

    report = validate_observations([observation])

    assert any(issue.category == CATEGORY_IMPOSSIBLE_VALUE for issue in report.issues)


def test_observed_at_after_ingested_at_flagged():
    observation = Observation(
        observation_id="firms:005",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=INGESTED_AT,
        latitude=37.5,
        longitude=-119.5,
        source_record_id="005",
        ingested_at=OBSERVED_AT,
    )

    report = validate_observations([observation])

    assert any(issue.category == CATEGORY_TIMESTAMPS for issue in report.issues)


def test_naive_timestamp_flagged():
    observation = Observation(
        observation_id="firms:006",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=datetime(2024, 8, 15, 10, 0),
        latitude=37.5,
        longitude=-119.5,
        source_record_id="006",
        ingested_at=INGESTED_AT,
    )

    report = validate_observations([observation])

    assert any(issue.category == CATEGORY_TIMESTAMPS for issue in report.issues)


def test_duplicate_observation_id_flagged_on_second_occurrence():
    observations = [_valid_observation("dup:001"), _valid_observation("dup:001")]

    report = validate_observations(observations)

    assert report.total_records == 2
    assert report.invalid_records == 1
    assert report.valid_records == 1

    duplicate_issues = [
        issue for issue in report.issues if issue.category == CATEGORY_DUPLICATE
    ]
    assert len(duplicate_issues) == 1


def test_quality_out_of_range_flagged():
    observation = Observation(
        observation_id="firms:007",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=OBSERVED_AT,
        latitude=37.5,
        longitude=-119.5,
        source_record_id="007",
        ingested_at=INGESTED_AT,
        quality=1.5,
    )

    report = validate_observations([observation])

    assert any(issue.category == CATEGORY_IMPOSSIBLE_VALUE for issue in report.issues)


def test_issues_by_category_counts():
    observations = [
        _valid_observation("a"),
        Observation(
            observation_id="b",
            source="NASA_FIRMS",
            product="VIIRS_SNPP_SP",
            observed_at=OBSERVED_AT,
            latitude=91.0,
            longitude=-119.5,
            source_record_id="b",
            ingested_at=INGESTED_AT,
        ),
    ]

    report = validate_observations(observations)

    assert report.issues_by_category[CATEGORY_COORDINATES] == 1


def test_validation_report_to_dict_serializable():
    report = validate_observations([_valid_observation()])
    payload = validation_report_to_dict(report)

    json.dumps(payload)

    assert payload["total_records"] == 1
    assert payload["valid_records"] == 1


def test_save_validation_report_roundtrip(tmp_path):
    report = validate_observations([_valid_observation()])
    output_path = tmp_path / "validation_report.json"

    result = save_validation_report(report, output_path)
    saved = json.loads(result.read_text(encoding="utf-8"))

    assert saved["total_records"] == 1
    assert saved["invalid_records"] == 0
