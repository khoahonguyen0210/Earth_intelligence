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

_STEP_REF_PATTERN = re.compile(r"^\$(?P<step_id>[^.]+)\.(?P<field>.+)$")

MAX_PLAN_STEPS = 8
MAX_QUESTION_CHARS = 1_000
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

    if step.tool not in TOOL_NAMES:
        return [
            f"{prefix}: unknown tool {step.tool!r}. Known tools: {sorted(TOOL_NAMES)}"
        ]

    tool = get_tool_schema(step.tool)

    try:
        jsonschema.validate(instance=step.input, schema=tool.input_schema)
    except jsonschema.exceptions.ValidationError as error:
        return [
            f"{prefix}: input does not match {tool.name}'s input schema: "
            f"{error.message}"
        ]

    errors: list[str] = []

    if "region" in step.input:
        errors.extend(_validate_region_literal(prefix, step.input["region"]))

    if "time_range" in step.input:
        errors.extend(_validate_time_range_literal(prefix, step.input["time_range"]))

    if "cutoff" in step.input:
        errors.extend(_validate_cutoff_literal(prefix, step.input["cutoff"]))

    errors.extend(_validate_depends_on(step, prefix, index, step_index))
    errors.extend(_validate_step_refs(step, prefix, index, plan, step_index))

    return errors


def _validate_region_literal(prefix: str, region_value: Any) -> list[str]:
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
