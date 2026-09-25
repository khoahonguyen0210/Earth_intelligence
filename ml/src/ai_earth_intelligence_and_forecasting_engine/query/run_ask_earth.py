from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_earth_intelligence_and_forecasting_engine.planner.generate_answer import (
    StepResult,
    generate_answer,
)
from ai_earth_intelligence_and_forecasting_engine.planner.generate_plan import (
    generate_plan,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import Plan
from ai_earth_intelligence_and_forecasting_engine.query.dispatch import (
    Backend,
    PlanExecution,
    execute_plan,
)

if TYPE_CHECKING:
    from google import genai


def _step_results(plan: Plan, execution: PlanExecution) -> dict[str, StepResult]:
    """Every step that produced an output, as generate_answer's own
    StepResult shape."""
    return {
        step.step_id: StepResult(
            step_id=step.step_id,
            tool=step.tool,
            result=execution.outputs[step.step_id],
            evidence=execution.evidence.get(step.step_id),
        )
        for step in plan.steps
        if step.step_id in execution.outputs
    }


def run_ask_earth(
    payload: dict[str, Any], client: genai.Client, backend: Backend
) -> dict[str, Any]:
    question = payload["question"]

    plan = generate_plan(question, client)
    execution = execute_plan(plan, backend)
    answer = generate_answer(plan, _step_results(plan, execution), client)

    grounding = answer.grounding
    return {
        "question": question,
        "answer": answer.summary,
        "grounding": (
            {
                "verified": grounding.verified,
                "checked": grounding.checked,
                "unsupported": list(grounding.unsupported),
                "unknown_tags": list(grounding.unknown_tags),
            }
            if grounding is not None
            else None
        ),
        "facts": [
            {
                "step_id": fact.step_id,
                "category": fact.category,
                "result": fact.result,
                "evidence": fact.evidence,
            }
            for fact in answer.facts
        ],
        "outputs": execution.outputs,
        "plan": {
            "steps": [
                {
                    "step_id": step.step_id,
                    "tool": step.tool,
                    "input": step.input,
                    "depends_on": list(step.depends_on),
                }
                for step in plan.steps
            ]
        },
    }
