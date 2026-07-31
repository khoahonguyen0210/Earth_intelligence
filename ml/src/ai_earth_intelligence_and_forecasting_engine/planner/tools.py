from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Shared fragments -- every tool that takes a region/time window uses the
# exact same shape Task 2.1 already locked (query.schema.RegionSpec/
# TimeRangeSpec), not a second, planner-specific region format.
REGION_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "A region exactly as locked by Task 2.1/2.2's RegionSpec. "
        "value's shape depends on kind: bbox -> [west, south, east, "
        "north]; coordinates -> [latitude, longitude]; named -> a "
        "region name string (e.g. 'california')."
    ),
    "properties": {
        "kind": {"type": "string", "enum": ["bbox", "coordinates", "named"]},
        "value": {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "number"}},
            ],
        },
    },
    "required": ["kind", "value"],
    "additionalProperties": False,
}

TIME_RANGE_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "A time window exactly as locked by Task 2.1/2.3's "
        "TimeRangeSpec -- ISO 8601 date/datetime strings; end is "
        "exclusive."
    ),
    "properties": {
        "start": {"type": "string"},
        "end": {"type": "string"},
    },
    "required": ["start", "end"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ToolSchema:
    """One entry in the planner's fixed tool surface (Task 7.1's "no
    arbitrary code execution": six named, bounded operations, nothing
    that takes a code string or shell command).

    `returns`/`output_fields` document the result shape for the
    validator (Task 7.2) and whoever wires up real dispatch (Tasks
    7.3/8.x); neither is part of the Claude tool wire format, which only
    has name/description/input_schema/strict -- see
    to_claude_tool_definition. `output_fields` is the top-level key set
    of a successful result, used to check a later step's reference to
    "field X of an earlier step's output" actually names something that
    step produces (Task 7.2's "workflow dependencies" check).
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    returns: str
    output_fields: frozenset[str]


def _strict_object_schema(
    properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    """A JSON Schema object safe for Claude's `strict: true` tool mode:
    additionalProperties is False and every property is required (strict
    mode has no notion of an optional property)."""
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


RESOLVE_REGION = ToolSchema(
    name="resolve_region",
    description=(
        "Resolve a raw region reference (bbox, coordinates, or a named "
        "California region) into deterministic geometry -- Task 2.2's "
        "normalize_region. Reads no Earth data. Every other tool also "
        "accepts the same raw region reference directly (each normalizes "
        "it internally, the same way run_analysis.py already does) -- "
        "call this one first only to confirm/preview what a region "
        "resolves to before committing to a real computation with it, "
        "not because another tool needs its output as an input."
    ),
    input_schema=_strict_object_schema(
        properties={"region": REGION_SPEC_SCHEMA},
        required=["region"],
    ),
    returns=(
        "A NormalizedRegion: bbox (west, south, east, north), geometry "
        "(GeoJSON polygon), source_kind, and an optional label."
    ),
    output_fields=frozenset({"bbox", "geometry", "source_kind", "label"}),
)

GET_DATA = ToolSchema(
    name="get_data",
    description=(
        "Retrieve a reference to the locked Earth dataset covering a "
        "region and time window -- one of the two time-ranged Phase 1 "
        "sources (static geography has no time window, so it is not "
        "reachable through this tool). Returns a summary (record count, "
        "provenance), never raw records: computing an actual number is "
        "calculate_statistics/generate_map's job, not something read "
        "off this tool's output."
    ),
    input_schema=_strict_object_schema(
        properties={
            "dataset": {"type": "string", "enum": ["firms", "era5_land"]},
            "region": REGION_SPEC_SCHEMA,
            "time_range": TIME_RANGE_SPEC_SCHEMA,
        },
        required=["dataset", "region", "time_range"],
    ),
    returns=(
        "A dataset reference: source, product, record_count, and the "
        "same provenance fields Task 1.8 already records."
    ),
    output_fields=frozenset({"source", "product", "record_count", "provenance"}),
)

CALCULATE_STATISTICS = ToolSchema(
    name="calculate_statistics",
    description=(
        "Compute a deterministic Earth statistic over real ingested "
        "data -- Task 2.4/2.9. The model never computes the number "
        "itself; this tool does. operation is exactly the set "
        "query.run_analysis.SUPPORTED_OPERATIONS dispatches today minus "
        "'map' (generate_map's job) -- other statistics.py functions "
        "not yet wired into that entry point are deliberately excluded "
        "rather than force-fit."
    ),
    input_schema=_strict_object_schema(
        properties={
            "region": REGION_SPEC_SCHEMA,
            "time_range": TIME_RANGE_SPEC_SCHEMA,
            "operation": {
                "type": "string",
                "enum": ["count", "daily_aggregate", "weekly_aggregate"],
            },
        },
        required=["region", "time_range", "operation"],
    ),
    returns=(
        "CountResult ({count}), DailyAggregateResult "
        "({daily: [{date, count}]}), or WeeklyAggregateResult "
        "({weekly: [{week_start, count}]}) depending on operation -- "
        "Task 2.9's locked result shapes."
    ),
    # The union across all three operations, since the actual key present
    # depends on which operation was run -- the validator's workflow-
    # dependency check is correspondingly coarse for this tool (it cannot
    # tell that a "weekly_aggregate" step never produces "count").
    output_fields=frozenset({"count", "daily", "weekly"}),
)

GENERATE_MAP = ToolSchema(
    name="generate_map",
    description=(
        "Build a map-ready result for a region/time window -- Task "
        "2.5's build_regional_map_result. A separate tool from "
        "calculate_statistics because its result is geometry-shaped "
        "(GeoJSON), not a number."
    ),
    input_schema=_strict_object_schema(
        properties={
            "region": REGION_SPEC_SCHEMA,
            "time_range": TIME_RANGE_SPEC_SCHEMA,
        },
        required=["region", "time_range"],
    ),
    returns=(
        "A GeoJSON FeatureCollection: one Feature per region, geometry "
        "+ properties.value/time/units/region_kind/region_label."
    ),
    output_fields=frozenset({"type", "features"}),
)

RUN_FORECAST = ToolSchema(
    name="run_forecast",
    description=(
        "Create an asynchronous 24-hour wildfire-risk forecast job -- "
        "the real POST /forecasts (Tasks 6.1-6.6). Returns immediately "
        "with a forecast_id and PENDING status; the caller must check "
        "status/evidence separately rather than assuming the forecast "
        "is already done."
    ),
    input_schema=_strict_object_schema(
        properties={
            "region": REGION_SPEC_SCHEMA,
            "cutoff": {
                "type": "string",
                "description": (
                    "ISO 8601 datetime: the data-availability instant "
                    "the forecast is made as of."
                ),
            },
        },
        required=["region", "cutoff"],
    ),
    returns="{forecast_id, status} per docs/forecast-api-contract.md.",
    output_fields=frozenset({"forecast_id", "status"}),
)

GET_RESULT_EVIDENCE = ToolSchema(
    name="get_result_evidence",
    description=(
        "Fetch the evidence record backing an already-computed result "
        "-- Task 2.6's Evidence. Never fabricates evidence for a result "
        "that does not exist; the validator rejects a plan that cites "
        "evidence before computing the result it belongs to."
    ),
    input_schema=_strict_object_schema(
        properties={
            "result_id": {
                "type": "string",
                "description": (
                    "An analysis id or forecast_id already returned by "
                    "another tool in this plan."
                ),
            },
        },
        required=["result_id"],
    ),
    returns=(
        "An Evidence record: dataset, period_start/end, region_kind/"
        "label/bbox, query_parameters, processing_version."
    ),
    output_fields=frozenset({
        "dataset",
        "period_start",
        "period_end",
        "region_kind",
        "region_label",
        "region_bbox",
        "query_parameters",
        "processing_version",
    }),
)

TOOL_SCHEMAS: tuple[ToolSchema, ...] = (
    RESOLVE_REGION,
    GET_DATA,
    CALCULATE_STATISTICS,
    GENERATE_MAP,
    RUN_FORECAST,
    GET_RESULT_EVIDENCE,
)

TOOL_NAMES: frozenset[str] = frozenset(tool.name for tool in TOOL_SCHEMAS)


def get_tool_schema(name: str) -> ToolSchema:
    for tool in TOOL_SCHEMAS:
        if tool.name == name:
            return tool

    raise KeyError(f"Unknown tool: {name!r}. Known tools: {sorted(TOOL_NAMES)}")


def to_claude_tool_definition(tool: ToolSchema) -> dict[str, Any]:
    """The exact shape client.messages.create(tools=[...]) expects:
    name/description/input_schema/strict only -- `returns` is internal
    documentation, not part of the real Claude tool-definition wire
    format."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "strict": True,
    }


def all_claude_tool_definitions() -> list[dict[str, Any]]:
    return [to_claude_tool_definition(tool) for tool in TOOL_SCHEMAS]
