# Planner Tool Schemas

This document defines the fixed set of tools that the AI planner can
use. The plan validator and the natural-language planner use these
definitions and do not redefine them.

## The eight tools

```text
resolve_region
get_data
calculate_statistics
generate_map
run_forecast
get_result_evidence
get_forecast_result
search_docs
```

All eight are defined in
`ai_earth_intelligence_and_forecasting_engine.planner.tools`
(`TOOL_SCHEMAS`). No tool can run arbitrary code: each one is a named,
limited operation with a fixed input shape, and none takes a code
string, a shell command or an open-ended expression.

Each tool matches a capability that already exists, instead of new
terms:

```text
resolve_region        -> query.region.normalize_region
get_data              -> the two time-ranged sources
calculate_statistics  -> query.run_analysis's non-map operations
generate_map          -> query.map_result.build_regional_map_result
run_forecast          -> POST /forecasts
get_result_evidence   -> query.evidence.Evidence
get_forecast_result   -> GET /forecasts/{id}/result, via query.forecast_summary
search_docs           -> rag.index.DocsIndex.search over docs/
```

`search_docs` answers questions about the system itself rather than
about fires. It returns up to five cited passages, as described in
`docs/rag.md`.

`get_forecast_result` exists because `run_forecast` returns only a job
id. Without it, the answer generator never sees a probability, so it
cannot say how risky a place is or why. It returns the five riskiest
cells, the maximum and mean probability over the region, and the SHAP
drivers described in `docs/explainability.md`.

The `operation` enum of `calculate_statistics`
(`count`, `daily_aggregate`, `weekly_aggregate`) is exactly
`query.run_analysis.SUPPORTED_OPERATIONS` without `"map"`, which belongs
to `generate_map`.
`tests/planner/test_tools.py::test_calculate_statistics_operations_match_run_analysis_dispatch`
checks this, so the tools cannot fall out of step with what the dispatch
code supports. `regional_aggregate` and `period_over_period_change` in
`statistics.py` are not connected to `run_analysis`, so they are not
tools either. They can be added when something first needs them.

`get_data` covers only `firms` and `era5_land`, not static geography.
Elevation and land cover have no time dimension, and every other tool
takes a `time_range`. Making `time_range` optional is not possible in
strict tool use (below), so static geography is simply not a `get_data`
dataset. It is also not one of the six query intents (count, aggregate,
compare, trend, map and forecast) that a planner would fetch on demand.

## Format: the Claude tool-definition format

```json
{
  "name": "resolve_region",
  "description": "...",
  "input_schema": { "type": "object", "properties": {...}, "required": [...], "additionalProperties": false },
  "strict": true
}
```

The planner was first built on the Claude API (see the provider note in
`docs/natural-language-planner.md`), so the tools use the format of
`client.messages.create(tools=[...])` (`input_schema`, not
`parameters`) instead of a new format. `to_claude_tool_definition` and
`all_claude_tool_definitions` build this shape from a `ToolSchema`.

Every tool sets `strict: true`. With strict mode, the model's tool input
must match `input_schema` exactly. That is why every schema here has
`additionalProperties: false` and lists every property in `required`;
strict mode has no optional properties. `_assert_strict_safe` in
`tests/planner/test_tools.py` checks this recursively, including inside
the shared `REGION_SPEC_SCHEMA` and `TIME_RANGE_SPEC_SCHEMA` parts that
every tool with a region or time window includes. The `kind` enum of
`REGION_SPEC_SCHEMA` is checked against `query.schema.VALID_REGION_KINDS`
for the same reason as the statistics operations above.

Strict mode checks only shape: the right keys and the right JSON types.
It does not check rules between fields or about the domain, such as
whether `value` fits `kind` (a bounding box `value` needs 4 numbers, and
a `named` value must be one of `NAMED_REGIONS`), whether a `cutoff` is a
valid datetime, or whether a `result_id` refers to something that
exists. `REGION_SPEC_SCHEMA.value` is typed only as
`anyOf: [string, number[]]`, not the full conditional shape. The finer
check belongs to the plan validator, which already has Python code for
it (the `ValueError`s raised by `normalize_region`), instead of a copy
in JSON Schema.

`ToolSchema.returns` describes each tool's result shape for the
validator and the dispatch code. It is not sent to the model:
`to_claude_tool_definition` removes it, because it is not part of the
Claude tool-definition format.

## Out of scope

This module does not call an LLM API, run a tool or validate a plan. It
only defines the tools. Which Python function each tool calls, and the
shape of plans and workflows, belong to the validator and the planner.

A correction made while building the plan validator: the description of
`resolve_region` first suggested that its `NormalizedRegion` output feeds
another tool's `region` argument. It does not. Every other tool takes
the same raw `RegionSpec` and normalizes it itself (as `run_analysis.py`
does), so `resolve_region` is a separate step for previewing and early
checking, not a stage that other tools depend on. The description in
`planner/tools.py` now says this.
