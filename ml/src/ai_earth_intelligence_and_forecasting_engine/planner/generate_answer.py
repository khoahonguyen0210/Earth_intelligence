from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ai_earth_intelligence_and_forecasting_engine.planner.validator import Plan

if TYPE_CHECKING:
    from google import genai

MODEL = "gemini-3.1-flash-lite"

# Which of the six locked tools (Task 7.1) contributes a fact to a final
# answer, and how that fact must be labeled (the handbook's
# observed/computed/predicted distinction). resolve_region is absent: it
# resolves geometry, it doesn't produce a fact about the world.
# get_result_evidence is absent too: it fetches metadata about a fact
# another step already produced, it isn't itself a fact.
RESULT_CATEGORY_BY_TOOL: dict[str, str] = {
    "get_data": "observed",
    "calculate_statistics": "computed",
    "generate_map": "computed",
    "run_forecast": "predicted",
}


@dataclass(frozen=True)
class StepResult:
    """The minimal shape Task 7.4 needs from one executed plan step: the
    real value a tool produced, and its evidence if it has any of its
    own. Phase 8's workflow engine is what will actually execute a Plan
    and produce these for real; this module only consumes them -- tests
    build StepResults from genuine calls to the real Task 2.x/6.x
    functions (query.statistics.count, query.evidence.build_evidence,
    ...) rather than fabricating result shapes."""

    step_id: str
    tool: str
    result: Any
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class GroundedFact:
    step_id: str
    category: str  # "observed" | "computed" | "predicted"
    result: Any
    evidence: dict[str, Any] | None


@dataclass(frozen=True)
class GroundedAnswer:
    question: str
    facts: tuple[GroundedFact, ...]
    summary: str


_NO_FACTS_SUMMARY = "No executed results are available to answer this question."

_SYSTEM_PROMPT = (
    "You explain already-computed Earth-intelligence results to a user. "
    "You summarize execution results and evidence only -- you never "
    "invent data, invent results, or state a number that was not given "
    "to you below. If the given facts don't actually answer the "
    "question, say so plainly instead of guessing. Every claim you make "
    "must be tagged inline as (observed), (computed), or (predicted), "
    "exactly matching the category already given for the fact it comes "
    "from -- never relabel a fact's category yourself."
)


def _assemble_facts(
    plan: Plan, results: dict[str, StepResult]
) -> tuple[GroundedFact, ...]:
    facts = []

    for step in plan.steps:
        category = RESULT_CATEGORY_BY_TOOL.get(step.tool)
        result = results.get(step.step_id)

        if category is None or result is None:
            continue

        facts.append(
            GroundedFact(
                step_id=step.step_id,
                category=category,
                result=result.result,
                evidence=result.evidence,
            )
        )

    return tuple(facts)


def _build_answer_prompt(question: str, facts: tuple[GroundedFact, ...]) -> str:
    fact_lines = [
        f"- [{fact.category}] step {fact.step_id!r}: result={json.dumps(fact.result)}"
        + (f", evidence={json.dumps(fact.evidence)}" if fact.evidence else "")
        for fact in facts
    ]

    return (
        f'Question: "{question}"\n\n'
        "Real, already-computed facts (nothing else exists -- do not "
        "add numbers, dates, or claims not listed here):\n"
        f"{chr(10).join(fact_lines)}\n\n"
        "Write a short, direct answer to the question using only the "
        "facts above, tagging every claim (observed), (computed), or "
        "(predicted) per its category."
    )


def generate_answer(
    plan: Plan, results: dict[str, StepResult], client: genai.Client
) -> GroundedAnswer:
    """Execution results + evidence -> a grounded final answer (Task
    7.4). Only steps whose tool is in RESULT_CATEGORY_BY_TOOL and which
    have a real StepResult contribute a fact; everything else is
    silently excluded rather than guessed at. With no facts at all, this
    returns a fixed "cannot answer" summary without calling the model --
    there being nothing to summarize, there's nothing to ask an LLM to
    write about."""
    facts = _assemble_facts(plan, results)

    if not facts:
        return GroundedAnswer(
            question=plan.question, facts=(), summary=_NO_FACTS_SUMMARY
        )

    response = client.models.generate_content(
        model=MODEL,
        contents=_build_answer_prompt(plan.question, facts),
        config={"system_instruction": _SYSTEM_PROMPT},
    )

    try:
        text = response.text
    except ValueError as exc:
        # See generate_plan.generate_plan: `.text` itself raises when
        # there is no text part (e.g. safety-blocked), rather than
        # exposing a separate refusal field to check first.
        raise ValueError(f"the answer generator refused to answer: {exc}") from exc

    if not text:
        raise ValueError("answer generator response contained no text output")

    return GroundedAnswer(question=plan.question, facts=facts, summary=text)
