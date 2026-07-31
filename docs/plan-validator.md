# Deterministic Plan Validator — LOCKED

This document freezes the plan shape and validator per Task 7.2 of the
Execution Handbook. It is not a brainstorming document. It builds on
`docs/planner-tool-schemas.md` (Task 7.1) rather than redefining it; Task
7.3 (natural-language planner) and Phase 8 (workflow engine) build
against this validator rather than reimplementing validation themselves.

## The plan shape

```python
@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool: str
    input: dict[str, Any]
    depends_on: tuple[str, ...] = ()

@dataclass(frozen=True)
class Plan:
    question: str
    steps: tuple[PlanStep, ...]
```

A plan is a static, upfront, fully-specified sequence of steps -- matching
`docs/PROMPT_SYSTEM.md`'s "natural language -> LLM -> structured plan ->
validator -> workflow" (the whole plan is produced once, then validated,
*then* executed), not a live turn-by-turn agentic loop. This is also why
`depends_on` exists as an explicit field rather than being inferred: a
future workflow engine (Phase 8's DAG, whose nodes already carry
`dependencies`) needs the ordering declared up front, before anything
runs.

## Cross-step references

A step's `input` may reference an earlier step's real output with a
plain string: `"$<step_id>.<field>"`, e.g.
`{"result_id": "$forecast.forecast_id"}`. This is deliberately just a
string, not a nested object marker, because it only makes sense on
string-typed fields (`result_id` today), which means it automatically
satisfies that field's `input_schema` type -- no special-casing needed
in the schema-shape check. `ToolSchema` (Task 7.1) gained an
`output_fields: frozenset[str]` for exactly this: checking that a
reference names a field the referenced tool's result actually has.
Resolving the reference to a real value is Phase 8's job; this validator
only checks the reference is well-formed.

In practice, the only tool whose output is ever worth referencing later
is `run_forecast` (it returns a `forecast_id`) feeding
`get_result_evidence`'s `result_id` -- `calculate_statistics`/
`generate_map` already return their evidence inline (mirroring
`run_analysis.py`'s synchronous `{result, evidence}` response), so a
plan answering a non-forecast question typically has no cross-step
references at all.

## The seven checks

Each maps to a concrete mechanism, reusing real, already-locked
validation rather than re-implementing it:

```text
tool name              -> step.tool must be one of planner.tools.TOOL_NAMES
input schema           -> jsonschema.validate against the tool's input_schema
region                 -> query.region.normalize_region (Task 2.2) -- same
                           ValueErrors normalize_region already raises
time range             -> query.time_range.normalize_time_range (Task 2.3)
allowed operations     -> the tool's own operation enum, via input schema
parameter ranges       -> region/time_range above, plus run_forecast's
                           cutoff via query.forecast_result.parse_cutoff
workflow dependencies  -> depends_on and $step.field references both
                           resolve to a real, earlier step whose tool
                           actually produces that field
```

Using the real `normalize_region`/`normalize_time_range`/`parse_cutoff`
functions (rather than duplicating range/format checks) means the
validator's notion of "valid region" can never drift from what the
actual Earth-analysis/forecast pipelines accept -- one source of truth,
checked by `tests/planner/test_validator.py`'s parametrized invalid-
region cases (degenerate bbox, unsupported named region, coordinates
outside the California grid).

## Rejection

```python
def validate_plan(plan: Plan) -> list[str]: ...       # [] means valid
def validate_plan_or_raise(plan: Plan) -> None: ...    # raises ValueError
```

`validate_plan` returns human-readable messages (empty list = valid),
mirroring the exact convention `query.schema.validate_structured_query`/
`query.forecast_result.validate_forecast_request` already use.
`validate_plan_or_raise` joins and raises, mirroring
`run_analysis.run_analysis`'s `if errors: raise ValueError("; ".join(errors))` --
this is what "invalid plans are rejected" concretely means: whoever
executes a plan (Phase 8) calls this before running anything.

## What this document does not define

No plan is ever produced by an LLM here -- that is Task 7.3's job; this
task only defines the shape a produced plan must have and rejects one
that doesn't. `calculate_statistics`'s `output_fields` is a union across
its three operations (`count`/`daily`/`weekly`), so a reference to a
field that operation doesn't actually produce (e.g. `count` from a
`weekly_aggregate` step) is not caught -- a real limitation, acceptable
because the only field genuinely referenced across steps in this tool
surface is `run_forecast`'s `forecast_id`. There is no retry/backoff
concept here (Task 6.6's is a different, execution-time retry); a
rejected plan is simply invalid, not retried.
