import pytest

from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    QueryIntent,
    RegionSpec,
    StructuredEarthQuery,
    TimeRangeSpec,
    validate_structured_query,
)


def test_query_intent_has_exactly_the_locked_values():
    assert {intent.value for intent in QueryIntent} == {
        "count",
        "aggregate",
        "compare",
        "trend",
        "map",
        "forecast",
    }


def test_query_intent_rejects_unknown_value():
    with pytest.raises(ValueError):
        QueryIntent("summarize")


def _valid_query(**overrides: object) -> StructuredEarthQuery:
    defaults: dict[str, object] = {
        "question": "How many fires occurred in California last week?",
        "intent": QueryIntent.COUNT,
        "region": RegionSpec(kind="named", value="California"),
        "time_range": TimeRangeSpec(start="2024-08-08", end="2024-08-15"),
        "operation": "count",
    }
    defaults.update(overrides)
    return StructuredEarthQuery(**defaults)  # type: ignore[arg-type]


def test_valid_query_has_no_validation_errors():
    assert validate_structured_query(_valid_query()) == []


def test_bbox_region_spec_carries_four_floats():
    region = RegionSpec(kind="bbox", value=(-124.5, 32.5, -114.0, 42.0))

    assert region.kind == "bbox"
    assert region.value == (-124.5, 32.5, -114.0, 42.0)


def test_coordinates_region_spec_carries_lat_lon():
    region = RegionSpec(kind="coordinates", value=(37.5, -119.5))

    assert region.value == (37.5, -119.5)


def test_validate_structured_query_flags_empty_question():
    query = _valid_query(question="   ")

    errors = validate_structured_query(query)

    assert "question must not be empty" in errors


def test_validate_structured_query_flags_empty_operation():
    query = _valid_query(operation="")

    errors = validate_structured_query(query)

    assert "operation must not be empty" in errors


def test_validate_structured_query_flags_unknown_region_kind():
    query = _valid_query(region=RegionSpec(kind="polygon", value="whatever"))

    errors = validate_structured_query(query)

    assert any("region.kind" in error for error in errors)


def test_validate_structured_query_flags_empty_time_range():
    query = _valid_query(time_range=TimeRangeSpec(start="", end=""))

    errors = validate_structured_query(query)

    assert "time_range.start must not be empty" in errors
    assert "time_range.end must not be empty" in errors


def test_validate_structured_query_accumulates_multiple_errors():
    query = _valid_query(
        question="",
        operation="",
        region=RegionSpec(kind="bogus", value=None),
    )

    errors = validate_structured_query(query)

    assert len(errors) == 3
