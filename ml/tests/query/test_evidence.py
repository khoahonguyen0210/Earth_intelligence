import json

from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    get_pipeline_version,
)
from ai_earth_intelligence_and_forecasting_engine.query.evidence import (
    attach_evidence,
    build_evidence,
    build_evidence_from_query,
    evidence_to_dict,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    QueryIntent,
    RegionSpec,
    StructuredEarthQuery,
    TimeRangeSpec,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)

REGION = normalize_region(RegionSpec(kind="named", value="california"))
TIME_RANGE = normalize_time_range(
    TimeRangeSpec(start="2024-08-01", end="2024-08-07")
)


def test_build_evidence_captures_dataset_period_region():
    evidence = build_evidence(
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=REGION,
        time_range=TIME_RANGE,
        query_parameters={"intent": "count"},
    )

    assert evidence.dataset == "NASA_FIRMS:VIIRS_SNPP_SP"
    assert evidence.period_start == TIME_RANGE.start.isoformat()
    assert evidence.period_end == TIME_RANGE.end.isoformat()
    assert evidence.region_kind == "named"
    assert evidence.region_label == "california"
    assert evidence.region_bbox == REGION.bbox
    assert evidence.query_parameters == {"intent": "count"}


def test_build_evidence_processing_version_matches_pipeline_version():
    evidence = build_evidence(
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=REGION,
        time_range=TIME_RANGE,
        query_parameters={},
    )

    assert evidence.processing_version == get_pipeline_version()
    assert evidence.processing_version != ""


def test_build_evidence_from_query_derives_parameters():
    query = StructuredEarthQuery(
        question="How many fires in California last week?",
        intent=QueryIntent.COUNT,
        region=RegionSpec(kind="named", value="california"),
        time_range=TimeRangeSpec(start="2024-08-01", end="2024-08-07"),
        operation="count",
    )

    evidence = build_evidence_from_query(
        query=query,
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=REGION,
        time_range=TIME_RANGE,
    )

    assert evidence.query_parameters == {
        "question": "How many fires in California last week?",
        "intent": "count",
        "operation": "count",
    }


def test_evidence_to_dict_is_json_serializable():
    evidence = build_evidence(
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=REGION,
        time_range=TIME_RANGE,
        query_parameters={"intent": "count"},
    )

    payload = evidence_to_dict(evidence)
    json.dumps(payload)

    assert payload["region_bbox"] == list(REGION.bbox)
    assert payload["region_label"] == "california"


def test_attach_evidence_wraps_result_and_evidence():
    evidence = build_evidence(
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=REGION,
        time_range=TIME_RANGE,
        query_parameters={"intent": "count"},
    )

    combined = attach_evidence(result={"count": 42}, evidence=evidence)
    json.dumps(combined)

    assert combined["result"] == {"count": 42}
    assert combined["evidence"]["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"


def test_evidence_region_label_is_none_for_bbox_region():
    bbox_region = normalize_region(
        RegionSpec(kind="bbox", value=(-124.5, 32.5, -114.0, 42.0))
    )

    evidence = build_evidence(
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=bbox_region,
        time_range=TIME_RANGE,
        query_parameters={},
    )

    assert evidence.region_label is None
    assert evidence.region_kind == "bbox"
