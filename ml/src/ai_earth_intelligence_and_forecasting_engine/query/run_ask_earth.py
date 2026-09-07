"""Task 14.1: the real natural-language-question pipeline the "Ask
Earth" page needs -- PROJECT_BIBLE's own product definition ("a user
asks a natural-language question about Earth... the system identifies
scope, retrieves data, executes a validated analysis, returns an
evidence-backed answer"), wired end to end for the first time:

    question -> generate_plan (Task 7.3, Gemini)
             -> validate_plan_or_raise (Task 7.2 -- generate_plan already
                calls this; a plan that fails validation never reaches
                execute_plan)
             -> execute_plan (this module's own dispatch.py -- the real
                dispatch every earlier task deferred)
             -> generate_answer (Task 7.4, Gemini, grounded only in the
                real outputs execute_plan produced)

Mirrors run_analysis.py/run_forecast.py's own shape: one function taking
the real dependencies as parameters (a genai.Client, a Backend), no
hidden global state, easy to call from a CLI or a test with a fake
client/backend.
"""

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
    """Every step that produced an output, as Task 7.4's own StepResult
    shape. generate_answer's _assemble_facts already excludes tools with
    no entry in RESULT_CATEGORY_BY_TOOL (resolve_region,
    get_result_evidence -- plumbing, not facts about the world), so this
    does not need to filter by tool itself."""
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

    return {
        "question": question,
        "answer": answer.summary,
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
