import json

import pytest

from ai_earth_intelligence_and_forecasting_engine.planner.tools import (
    CALCULATE_STATISTICS,
    REGION_SPEC_SCHEMA,
    RESOLVE_REGION,
    RUN_FORECAST,
    TOOL_SCHEMAS,
    all_claude_tool_definitions,
    get_tool_schema,
    to_claude_tool_definition,
)
from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    SUPPORTED_OPERATIONS,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    VALID_REGION_KINDS,
)


def _assert_strict_safe(schema: dict) -> None:
    """Recursively verifies the Claude strict-tool-use invariant: every
    object node has additionalProperties: False and lists every one of
    its properties as required (strict mode has no optional property)."""
    if schema.get("type") != "object":
        return

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())

    for property_schema in schema["properties"].values():
        _assert_strict_safe(property_schema)
        for variant in property_schema.get("anyOf", []):
            _assert_strict_safe(variant)


def test_tool_schemas_has_exactly_the_six_locked_tools():
    assert {tool.name for tool in TOOL_SCHEMAS} == {
        "resolve_region",
        "get_data",
        "calculate_statistics",
        "generate_map",
        "run_forecast",
        "get_result_evidence",
    }


@pytest.mark.parametrize("tool", TOOL_SCHEMAS, ids=lambda tool: tool.name)
def test_every_tool_input_schema_is_strict_safe(tool):
    _assert_strict_safe(tool.input_schema)


def test_get_tool_schema_returns_the_matching_tool():
    assert get_tool_schema("run_forecast") is RUN_FORECAST


def test_get_tool_schema_raises_for_an_unknown_tool():
    with pytest.raises(KeyError):
        get_tool_schema("execute_python")


def test_to_claude_tool_definition_has_exactly_the_wire_format_fields():
    definition = to_claude_tool_definition(RESOLVE_REGION)

    assert set(definition.keys()) == {"name", "description", "input_schema", "strict"}
    assert definition["name"] == "resolve_region"
    assert definition["strict"] is True
    assert definition["input_schema"] == RESOLVE_REGION.input_schema


def test_all_claude_tool_definitions_returns_one_per_tool():
    definitions = all_claude_tool_definitions()

    assert len(definitions) == len(TOOL_SCHEMAS)
    assert {definition["name"] for definition in definitions} == {
        tool.name for tool in TOOL_SCHEMAS
    }


def test_all_claude_tool_definitions_are_json_serializable():
    json.dumps(all_claude_tool_definitions())


def test_region_spec_schema_kind_enum_matches_the_locked_valid_kinds():
    assert set(REGION_SPEC_SCHEMA["properties"]["kind"]["enum"]) == VALID_REGION_KINDS


def test_calculate_statistics_operations_match_run_analysis_dispatch():
    operation_schema = CALCULATE_STATISTICS.input_schema["properties"]["operation"]
    tool_operations = set(operation_schema["enum"])

    # "map" is generate_map's tool, not calculate_statistics's, so it is
    # the one supported operation deliberately excluded here.
    assert tool_operations == SUPPORTED_OPERATIONS - {"map"}
