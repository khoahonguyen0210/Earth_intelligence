# Deterministic Plan Validator

This document defines the plan shape and the validator. It builds on
`docs/planner-tool-schemas.md`. The natural-language planner and the
workflow engine use this validator instead of writing their own checks.

## Plan shape

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

A plan is a fixed, complete list of steps written before anything runs.
It follows the flow "natural language -> LLM -> structured plan ->
validator -> workflow": the whole plan is produced once, checked, and
only then executed. It is not a loop in which the model acts turn by
turn. That is also why `depends_on` is an explicit field and not
inferred: the workflow engine (the DAG, whose nodes have
`dependencies`) needs the order stated before anything runs.

## References between steps

A step's `input` may refer to an earlier step's output with a plain
string, `"$<step_id>.<field>"`, for example
`{"result_id": "$forecast.forecast_id"}`. It is a plain string, not a
nested marker object, because a reference only makes sense in a string
field (today only `result_id`). So it always matches that field's type
in `input_schema`, and the schema check needs no special case.
`ToolSchema` has an `output_fields: frozenset[str]` for checking that a
reference names a field that the referenced tool's result actually
has. Replacing the reference with a value is the workflow engine's job;
the validator only checks that the reference is well formed.

In practice, the only output worth referring to later is the
`forecast_id` from `run_forecast`, used as `result_id` by
`get_result_evidence`. `calculate_statistics` and `generate_map` already
return their evidence with the result (like the synchronous
`{result, evidence}` response of `run_analysis.py`), so a plan for a
question that is not a forecast usually has no references between steps.

## The seven checks

Each check uses existing validation code instead of a new copy:

```text
tool name              -> step.tool must be one of planner.tools.TOOL_NAMES
input schema           -> jsonschema.validate against the tool's input_schema
region                 -> query.region.normalize_region, with the same
                          ValueErrors that normalize_region already raises
time range             -> query.time_range.normalize_time_range
allowed operations     -> the tool's own operation enum, through the input schema
parameter ranges       -> region and time_range above, plus run_forecast's
                          cutoff through query.forecast_result.parse_cutoff
workflow dependencies  -> depends_on and $step.field references both
                          point to an existing earlier step whose tool
                          produces that field
```

Because the validator calls `normalize_region`, `normalize_time_range`
and `parse_cutoff` instead of repeating their range and format checks,
its idea of a valid region can never differ from what the Earth
analysis and forecast pipelines accept. There is one source of truth.
`tests/planner/test_validator.py` checks this with parametrized invalid
regions (an empty bounding box, an unsupported named region, and
coordinates outside the California grid).

## Rejection

```python
def validate_plan(plan: Plan) -> list[str]: ...       # [] means valid
def validate_plan_or_raise(plan: Plan) -> None: ...    # raises ValueError
```

`validate_plan` returns readable messages (an empty list means valid),
the same convention as `query.schema.validate_structured_query` and
`query.forecast_result.validate_forecast_request`.
`validate_plan_or_raise` joins the messages and raises, like
`if errors: raise ValueError("; ".join(errors))` in
`run_analysis.run_analysis`. This is what "invalid plans are rejected"
means in practice: the code that runs a plan calls this before running
anything.

## Limits

- The validator does not produce plans; the natural-language planner
  does. This document only defines the shape a plan must have and
  rejects plans that do not have it.
- `output_fields` for `calculate_statistics` is the union over its three
  operations (`count`, `daily` and `weekly`). A reference to a field
  that the step's operation does not produce (for example `count` from a
  `weekly_aggregate` step) is not caught. This is acceptable, because the
  only field that is actually referenced across steps is the
  `forecast_id` from `run_forecast`.
- There is no retry here. Retries happen at execution time; a rejected
  plan is simply invalid.
