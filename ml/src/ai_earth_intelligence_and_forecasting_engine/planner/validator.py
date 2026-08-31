from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import jsonschema

from ai_earth_intelligence_and_forecasting_engine.planner.tools import (
    TOOL_NAMES,
    get_tool_schema,
)
from ai_earth_intelligence_and_forecasting_engine.query.forecast_result import (
    parse_cutoff,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    RegionSpec,
    TimeRangeSpec,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)

# A later step's input may reference an earlier step's real output with a
# plain string "$<step_id>.<field>" instead of a literal value -- e.g.
# get_result_evidence's result_id referencing "$forecast.forecast_id"
# after an earlier step named "forecast" ran run_forecast. This is
# intentionally just a string (not a nested object marker): every field
# in this tool surface that plausibly needs a cross-step value
# (result_id) is itself string-typed, so a reference already satisfies
# that field's JSON Schema type with no special-casing required in the
# schema-shape check below. Resolving it to a real value is Tasks
# 7.3/8.x's job; this module only checks the reference is well-formed.
_STEP_REF_PATTERN = re.compile(r"^\$(?P<step_id>[^.]+)\.(?P<field>.+)$")

# Task 13.4 (LLM tool restrictions): bounds on what a model-written plan
# may ask for, enforced here rather than trusted to the prompt. Real
# plans are small -- the handbook's example DAG has 6 nodes and no
# planner-benchmark case needs more than 2 matching steps -- so 8 steps
# only ever stops a runaway plan, whose every step could start real work
# (a run_forecast step queues a Python job). A step id is a short
# identifier, since it is echoed into later steps' "$step_id.field"
# references and into logs. The question bound matches the API's own
# (RequestShape.MAX_QUESTION on the backend).
MAX_PLAN_STEPS = 8
MAX_QUESTION_CHARS = 1_000
# fullmatch, not match with "$": "$" also matches before a trailing newline.
_STEP_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}")


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool: str
    input: dict[str, Any]
    depends_on: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Plan:
    question: str
    steps: tuple[PlanStep, ...]


def _parse_step_ref(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None

    match = _STEP_REF_PATTERN.match(value)

    if match is None:
        return None

    return match.group("step_id"), match.group("field")


def _find_step_refs(value: Any) -> list[tuple[str, str]]:
    ref = _parse_step_ref(value)

    if ref is not None:
        return [ref]

    if isinstance(value, dict):
        return [ref for nested in value.values() for ref in _find_step_refs(nested)]

    if isinstance(value, list):
        return [ref for nested in value for ref in _find_step_refs(nested)]

    return []


def validate_plan(plan: Plan) -> list[str]:
    """Returns a list of human-readable error messages; a valid plan
    returns an empty list. Checks, per the Execution Handbook's Task 7.2:
    tool name, input schema, region, time range, allowed operations
    (calculate_statistics.operation), parameter ranges (bbox/coordinates/
    named-region/cutoff validity), and workflow dependencies (depends_on
    and $step.field references both point to a real, earlier step whose
    tool actually produces that field)."""
    if not plan.steps:
        return ["a plan must have at least one step"]

    if len(plan.steps) > MAX_PLAN_STEPS:
        return [
            f"a plan may have at most {MAX_PLAN_STEPS} steps, got {len(plan.steps)}"
        ]

    errors: list[str] = []

    if len(plan.question) > MAX_QUESTION_CHARS:
        errors.append(f"question exceeds {MAX_QUESTION_CHARS} characters")
    step_index: dict[str, int] = {}

    for index, step in enumerate(plan.steps):
        if not _STEP_ID_PATTERN.fullmatch(step.step_id):
            errors.append(
                f"step {step.step_id[:40]!r}: step_id must be a letter followed by "
                "up to 31 letters, digits or underscores"
            )
        if step.step_id in step_index:
            errors.append(f"step {step.step_id!r}: duplicate step_id")
        else:
            step_index[step.step_id] = index

    for index, step in enumerate(plan.steps):
        errors.extend(_validate_step(step, index, plan, step_index))

    return errors


def validate_plan_or_raise(plan: Plan) -> None:
    errors = validate_plan(plan)

    if errors:
        raise ValueError("; ".join(errors))


def _validate_step(
    step: PlanStep, index: int, plan: Plan, step_index: dict[str, int]
) -> list[str]:
    prefix = f"step {step.step_id!r}"

    # 1. tool name
    if step.tool not in TOOL_NAMES:
        return [
            f"{prefix}: unknown tool {step.tool!r}. Known tools: {sorted(TOOL_NAMES)}"
        ]

    tool = get_tool_schema(step.tool)

    # 2. input schema (also covers 5. allowed operations, via the tool's
    # own operation enum)
    try:
        jsonschema.validate(instance=step.input, schema=tool.input_schema)
    except jsonschema.exceptions.ValidationError as error:
        return [
            f"{prefix}: input does not match {tool.name}'s input schema: "
            f"{error.message}"
        ]

    errors: list[str] = []

    # 3 + 6. region (parameter ranges: bbox/coordinates/named-region validity)
    if "region" in step.input:
        errors.extend(_validate_region_literal(prefix, step.input["region"]))

    # 4 + 6. time range (parameter ranges: start-before-end, parseable)
    if "time_range" in step.input:
        errors.extend(_validate_time_range_literal(prefix, step.input["time_range"]))

    # 6. parameter ranges: run_forecast's cutoff
    if "cutoff" in step.input:
        errors.extend(_validate_cutoff_literal(prefix, step.input["cutoff"]))

    # 7. workflow dependencies
    errors.extend(_validate_depends_on(step, prefix, index, step_index))
    errors.extend(_validate_step_refs(step, prefix, index, plan, step_index))

    return errors


def _validate_region_literal(prefix: str, region_value: Any) -> list[str]:
    # No step-reference check here: region's schema type is "object", so
    # a $ref string could never have passed the input-schema validation
    # this runs after -- only cutoff (string-typed) can actually carry one.
    try:
        normalize_region(
            RegionSpec(kind=region_value["kind"], value=region_value["value"])
        )
    except ValueError as error:
        return [f"{prefix}: invalid region: {error}"]

    return []


def _validate_time_range_literal(prefix: str, time_range_value: Any) -> list[str]:
    try:
        normalize_time_range(
            TimeRangeSpec(start=time_range_value["start"], end=time_range_value["end"])
        )
    except ValueError as error:
        return [f"{prefix}: invalid time_range: {error}"]

    return []


def _validate_cutoff_literal(prefix: str, cutoff_value: Any) -> list[str]:
    if _parse_step_ref(cutoff_value) is not None:
        return []

    try:
        parse_cutoff(cutoff_value)
    except ValueError:
        return [f"{prefix}: cutoff must be an ISO 8601 datetime, got: {cutoff_value!r}"]

    return []


def _validate_depends_on(
    step: PlanStep, prefix: str, index: int, step_index: dict[str, int]
) -> list[str]:
    errors: list[str] = []

    for dependency in step.depends_on:
        if dependency not in step_index:
            errors.append(
                f"{prefix}: depends_on references unknown step {dependency!r}"
            )
        elif step_index[dependency] >= index:
            errors.append(
                f"{prefix}: depends_on references step {dependency!r}, "
                "which does not come before it"
            )

    return errors


def _validate_step_refs(
    step: PlanStep,
    prefix: str,
    index: int,
    plan: Plan,
    step_index: dict[str, int],
) -> list[str]:
    errors: list[str] = []

    for ref_step_id, ref_field in _find_step_refs(step.input):
        if ref_step_id not in step_index:
            errors.append(f"{prefix}: references unknown step {ref_step_id!r}")
            continue

        ref_index = step_index[ref_step_id]

        if ref_index >= index:
            errors.append(
                f"{prefix}: references step {ref_step_id!r}, "
                "which does not come before it"
            )
            continue

        if ref_step_id not in step.depends_on:
            errors.append(
                f"{prefix}: references step {ref_step_id!r} "
                "without declaring it in depends_on"
            )

        referenced_tool = get_tool_schema(plan.steps[ref_index].tool)

        if ref_field not in referenced_tool.output_fields:
            errors.append(
                f"{prefix}: references field {ref_field!r} of step {ref_step_id!r} "
                f"({referenced_tool.name}), which only produces: "
                f"{sorted(referenced_tool.output_fields)}"
            )

    return errors
