# Planner Tool Schemas — LOCKED

This document freezes the AI planner's fixed tool schemas. It is not a
brainstorming document. The deterministic plan validator and the
natural-language planner build against this surface rather than
redefining it.

## The eight tools, and nothing else

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
(`TOOL_SCHEMAS`). "No arbitrary code execution" holds by construction: every tool is a named,
bounded operation with a fixed input shape: none takes a code string, a
shell command, or an open-ended expression.

Each tool mirrors a capability that already exists rather than inventing
new vocabulary:

```text
resolve_region        -> query.region.normalize_region
get_data               -> the two time-ranged sources
calculate_statistics   -> query.run_analysis's non-map operations
generate_map           -> query.map_result.build_regional_map_result
run_forecast           -> POST /forecasts
get_result_evidence    -> query.evidence.Evidence
get_forecast_result    -> GET /forecasts/{id}/result, via query.forecast_summary
search_docs            -> rag.index.DocsIndex.search over docs/
```

`search_docs` answers questions about the system itself rather than
about fires. It returns up to five cited passages, described in
`docs/rag.md`.

`get_forecast_result` exists because `run_forecast` returns only a job
id. Without it the answer generator never sees a probability, so it
cannot say how risky a place is or why. It returns the five riskiest
cells, the maximum and mean probability over the region, and the SHAP
drivers described in `docs/explainability.md`.

`calculate_statistics`'s `operation` enum
(`count`/`daily_aggregate`/`weekly_aggregate`) is exactly
`query.run_analysis.SUPPORTED_OPERATIONS` minus `"map"` (which
`generate_map` owns instead) -- checked by
`tests/planner/test_tools.py::test_calculate_statistics_operations_match_run_analysis_dispatch`,
so the tool surface cannot silently drift from what the dispatch code
actually supports. `statistics.py`'s `regional_aggregate`/
`period_over_period_change` are not wired into `run_analysis` today (see
that module's own comment) and so are correctly absent here too --
adding them is whatever future task first gives them a real caller, not
this one.

`get_data` is scoped to `firms`/`era5_land` only, not static geography:
DEM/land-cover have no time dimension, and every other tool in this
surface takes a `time_range`. Rather than making `time_range` optional
(which strict tool use, below, does not support), static geography is
simply not one of `get_data`'s reachable datasets -- it isn't one of the
six query intents (count/aggregate/compare/trend/map/forecast) a planner
would fetch on demand anyway.

## Shape: Claude tool-definition wire format, not an invented one

```json
{
  "name": "resolve_region",
  "description": "...",
  "input_schema": { "type": "object", "properties": {...}, "required": [...], "additionalProperties": false },
  "strict": true
}
```

This is deliberately the real `client.messages.create(tools=[...])`
shape (`input_schema`, not `parameters`), not a planner-specific format
invented ahead of the natural-language planner actually calling the API.
`to_claude_tool_definition`/`all_claude_tool_definitions` produce this
exact shape from a `ToolSchema`.

`strict: true` is set on every tool: Claude then guarantees a
`tool_use.input` validates exactly against `input_schema`, which is why
every schema here has `additionalProperties: false` with every declared
property listed in `required` (strict mode has no notion of an optional
property) -- `tests/planner/test_tools.py`'s
`_assert_strict_safe` checks this recursively, including through the
shared `REGION_SPEC_SCHEMA`/`TIME_RANGE_SPEC_SCHEMA` fragments every
region/time-window-taking tool embeds. `REGION_SPEC_SCHEMA`'s `kind`
enum is checked against `query.schema.VALID_REGION_KINDS` for the same
no-drift reason as the statistics operations above.

Strict mode only guarantees shape (the right keys, the right JSON
types). It does not check cross-field or domain rules -- whether `value`
actually matches `kind` (a bbox `value` needs 4 numbers, a `named` value
needs to be one of `NAMED_REGIONS`), whether a `cutoff` is a real
parseable datetime, whether a `result_id` refers to something that
exists. `REGION_SPEC_SCHEMA.value` is intentionally typed as
`anyOf: [string, number[]]`, not the full conditional shape, because
that finer-grained check belongs to the deterministic plan validator
(the handbook's own list -- "region", "parameter ranges" -- names this
as validator work), which already has real Python doing exactly this
validation (`normalize_region`'s own `ValueError`s) to check plans
against, rather than duplicating it in JSON Schema.

`ToolSchema.returns` documents each tool's result shape (for the
validator and for whoever wires up real dispatch in later planner and
workflow-engine work) but is not sent to the model -- `to_claude_tool_definition` strips it, since
it is not part of the real Claude tool-definition format.

## What this document does not define

Nothing here calls the Claude API, executes a tool, or validates a
plan -- this document only fixes the tool surface those later tasks build
against. Which Python function each tool's `dispatch` actually calls,
and the plan/workflow shape itself, are the validator's and the
planner's job, not this one's.

Correction found while building the deterministic plan validator: `resolve_region`'s tool
description originally implied its `NormalizedRegion` output feeds into
another tool's `region` argument. It does not -- every other tool
accepts the same raw `RegionSpec` directly and normalizes it internally
(the same way `run_analysis.py` already does), so `resolve_region` is a
standalone preview/early-validation step, not a pipeline stage other
tools depend on. The description in `planner/tools.py` has been
corrected to say this.
