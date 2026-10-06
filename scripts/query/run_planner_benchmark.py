import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.planner.benchmark_set import (
    BENCHMARK_CASES,
    CaseOutcome,
    score_case,
    summarize,
)
from ai_earth_intelligence_and_forecasting_engine.planner.generate_plan import (
    MODEL,
    generate_plan,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import Plan
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

REPORT_OUTPUT_PATH = Path("data/processed/planner_benchmark/benchmark_report.json")


def _plan_to_dict(plan: Plan | None) -> dict[str, object] | None:
    if plan is None:
        return None

    return {
        "question": plan.question,
        "steps": [
            {
                "step_id": step.step_id,
                "tool": step.tool,
                "input": step.input,
                "depends_on": list(step.depends_on),
            }
            for step in plan.steps
        ],
    }


def _outcome_to_dict(outcome: CaseOutcome) -> dict[str, object]:
    return {
        "name": outcome.case.name,
        "category": outcome.case.category,
        "question": outcome.case.question,
        "expect_valid_plan": outcome.case.expect_valid_plan,
        "valid_plan": outcome.valid_plan,
        "valid_plan_as_expected": outcome.valid_plan_as_expected,
        "intent_correct": outcome.intent_correct,
        "region_correct": outcome.region_correct,
        "time_correct": outcome.time_correct,
        "execution_ok": outcome.execution_ok,
        "contained": outcome.contained,
        "error": outcome.error,
        "plan": _plan_to_dict(outcome.plan),
    }


def plan_with_retry(question: str, client: genai.Client, attempts: int = 5) -> Plan:
    for attempt in range(attempts):
        try:
            return generate_plan(question, client)
        except ValueError:
            raise
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def main() -> None:
    client = genai.Client(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=6, initial_delay=3.0, http_status_codes=[429, 500, 503]
            )
        )
    )
    outcomes: list[CaseOutcome] = []

    for case in BENCHMARK_CASES:
        plan: Plan | None = None
        error: Exception | None = None

        try:
            plan = plan_with_retry(case.question, client)
        except ValueError as exc:
            error = exc

        outcome = score_case(case, plan, error)
        outcomes.append(outcome)

        if outcome.valid_plan_as_expected is None:
            status = "OBSERVED"
        elif outcome.valid_plan_as_expected:
            status = "PASS"
        else:
            status = "FAIL"

        print(f"[{status}] {case.name} ({case.category})")
        if outcome.error:
            print(f"    error: {outcome.error}")

    summary = summarize(outcomes)

    report = {
        "model": MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cases": [_outcome_to_dict(outcome) for outcome in outcomes],
    }

    REPORT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved planner benchmark report to: {REPORT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
