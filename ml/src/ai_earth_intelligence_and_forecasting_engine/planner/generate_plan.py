from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ai_earth_intelligence_and_forecasting_engine.planner.tools import (
    TOOL_NAMES,
    TOOL_SCHEMAS,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    MAX_QUESTION_CHARS,
    Plan,
    PlanStep,
    validate_plan_or_raise,
)

if TYPE_CHECKING:
    from google import genai

MODEL = "gemini-3.1-flash-lite"

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


def _to_gemini_schema(schema: Any) -> Any:
    """Gemini's response_schema is a restricted, OpenAPI-3.0-style
    dialect that does not support the "additionalProperties" keyword at
    all -- a real incompatibility discovered against the live API
    (unlike OpenAI, which *requires* it under strict structured output,
    Gemini rejects the request outright if it is present). PLAN_OUTPUT_
    SCHEMA is authored as an ordinary JSON Schema -- this strips the one
    keyword Gemini's dialect cannot parse before it is sent as
    response_schema, without changing the schema used everywhere else
    (documentation, the tool-enum test)."""
    if isinstance(schema, dict):
        return {
            key: _to_gemini_schema(value)
            for key, value in schema.items()
            if key != "additionalProperties"
        }
    if isinstance(schema, list):
        return [_to_gemini_schema(item) for item in schema]
    return schema


def _gemini_plan_schema() -> dict[str, Any]:
    """PLAN_OUTPUT_SCHEMA's `input` is deliberately a bare, tool-agnostic
    object (see its own docstring above) so Task 7.2's validator does
    the real per-tool enforcement, not this schema. Gemini's schema-
    constrained decoding takes an object schema with no declared
    properties literally, though: it always emits an empty object for
    it rather than filling it in from prompt context (confirmed against
    the live API -- every current model, not a weak-model quirk).
    Substituting the union of every real tool's already-defined
    input_schema (the same TOOL_SCHEMAS objects Task 7.2's validator
    checks against, and the same ones already rendered as text in the
    system prompt) fixes this without loosening or duplicating real
    validation: Gemini gets a concrete shape to aim for per tool, but
    Task 7.2 still re-validates the result against the specific tool
    each step actually names."""
    schema = _to_gemini_schema(PLAN_OUTPUT_SCHEMA)
    schema["properties"]["steps"]["items"]["properties"]["input"] = {
        "anyOf": [_to_gemini_schema(tool.input_schema) for tool in TOOL_SCHEMAS]
    }
    return schema


_GEMINI_PLAN_SCHEMA = _gemini_plan_schema()


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


def generate_plan(question: str, client: genai.Client) -> Plan:
    """Natural language -> LLM -> structured plan -> validator (Task
    7.2's validate_plan_or_raise) -- docs/PROMPT_SYSTEM.md's Phase 7
    flow. The LLM cannot bypass the validator: there is no path in this
    function that returns a Plan which has not already passed
    validate_plan_or_raise. An invalid plan raises ValueError here; it
    is never handed to a workflow unchecked.

    Task 13.4: an overlong question is refused before the model is ever
    called -- the validator would reject its plan anyway, and the call
    itself is the cost.
    """
    if len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} characters")

    response = client.models.generate_content(
        model=MODEL,
        contents=question,
        config={
            "system_instruction": _SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": _GEMINI_PLAN_SCHEMA,
        },
    )

    try:
        text = response.text
    except ValueError as exc:
        # The SDK's `.text` accessor itself raises ValueError when a
        # response has no text part -- e.g. blocked by a safety filter --
        # rather than exposing a separate refusal field to check first.
        raise ValueError(f"the planner refused to answer: {exc}") from exc

    if not text:
        raise ValueError("planner response contained no text/JSON output")

    payload = json.loads(text)
    plan = parse_plan(question, payload)

    validate_plan_or_raise(plan)

    return plan
