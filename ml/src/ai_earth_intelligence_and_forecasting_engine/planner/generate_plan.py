from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ai_earth_intelligence_and_forecasting_engine.planner.tools import (
    TOOL_NAMES,
    TOOL_SCHEMAS,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    Plan,
    PlanStep,
    validate_plan_or_raise,
)

if TYPE_CHECKING:
    import anthropic

MODEL = "claude-opus-5"

# The whole plan is one structured-output JSON document, not a live
# tool-calling loop: docs/PROMPT_SYSTEM.md's flow is "LLM -> structured
# plan -> validator -> workflow" -- the entire plan exists before
# anything executes, so a step that needs an earlier step's real value
# (not known yet) uses the $step_id.field string convention
# (planner.validator._STEP_REF_PATTERN) instead of a literal.
#
# `input` is intentionally left as a bare object here, not validated
# per-tool at this layer: Task 7.2's validate_plan_or_raise is what
# actually checks a step's input against its specific tool's schema.
# Keeping this outer schema loose and letting the deterministic
# validator do the real enforcement is the point of the LLM -> validator
# boundary this task exists to build -- not a gap to close here.
PLAN_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "tool": {"type": "string", "enum": sorted(TOOL_NAMES)},
                    "input": {"type": "object"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["step_id", "tool", "input", "depends_on"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["steps"],
    "additionalProperties": False,
}


def _build_system_prompt() -> str:
    tool_sections = "\n\n".join(
        f"### {tool.name}\n"
        f"{tool.description}\n\n"
        f"Input schema:\n{json.dumps(tool.input_schema, indent=2)}\n\n"
        f"Returns: {tool.returns}"
        for tool in TOOL_SCHEMAS
    )

    return (
        "You are the planning layer of an Earth-intelligence system. "
        "Given a natural-language question, produce a plan: an ordered "
        "list of steps, each invoking exactly one of the tools below. "
        "You do not compute any numbers or run any code yourself -- you "
        "only select tools and fill in their inputs.\n\n"
        f"{tool_sections}\n\n"
        "Rules:\n"
        '- Every step\'s "tool" must be exactly one of the names above.\n'
        '- A step\'s "input" must match that tool\'s input schema.\n'
        "- To use an earlier step's real output as a later step's input "
        'value, write the string "$<step_id>.<field>" instead of a '
        'literal value (e.g. "$forecast.forecast_id"), and list that '
        'step_id in the later step\'s "depends_on". Only run_forecast '
        "produces an id worth referencing this way; "
        "calculate_statistics/generate_map already return their own "
        "evidence inline, so a plan answering a count/aggregate/map "
        "question typically needs no cross-step references at all.\n"
        "- Do not invent tools, input fields, or values outside what is "
        "described above."
    )


_SYSTEM_PROMPT = _build_system_prompt()


def parse_plan(question: str, payload: dict[str, Any]) -> Plan:
    """Builds a Plan from an already-parsed JSON payload matching
    PLAN_OUTPUT_SCHEMA. Public (not just an internal step of
    generate_plan) so a logged/replayed LLM response can be turned back
    into a Plan without a fresh API call."""
    steps = tuple(
        PlanStep(
            step_id=raw_step["step_id"],
            tool=raw_step["tool"],
            input=raw_step["input"],
            depends_on=tuple(raw_step["depends_on"]),
        )
        for raw_step in payload["steps"]
    )

    return Plan(question=question, steps=steps)


def generate_plan(question: str, client: anthropic.Anthropic) -> Plan:
    """Natural language -> LLM -> structured plan -> validator (Task
    7.2's validate_plan_or_raise) -- docs/PROMPT_SYSTEM.md's Phase 7
    flow. The LLM cannot bypass the validator: there is no path in this
    function that returns a Plan which has not already passed
    validate_plan_or_raise. An invalid plan raises ValueError here; it
    is never handed to a workflow unchecked.
    """
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
        output_config={"format": {"type": "json_schema", "schema": PLAN_OUTPUT_SCHEMA}},
    )

    if response.stop_reason == "refusal":
        raise ValueError(f"the planner refused to answer: {response.stop_details}")

    text_blocks = [block.text for block in response.content if block.type == "text"]

    if not text_blocks:
        raise ValueError("planner response contained no text/JSON output")

    payload = json.loads(text_blocks[0])
    plan = parse_plan(question, payload)

    validate_plan_or_raise(plan)

    return plan
