from __future__ import annotations

from dataclasses import dataclass

from ai_earth_intelligence_and_forecasting_engine.planner.validator import Plan

CATEGORIES: tuple[str, ...] = (
    "count",
    "trend",
    "compare",
    "map",
    "forecast",
    "ambiguous",
    "unsupported",
)


@dataclass(frozen=True)
class BenchmarkCase:
    """One fixed query for the planner benchmark.

    `expect_valid_plan` is None for "ambiguous" cases; those cases are
    recorded for observability only, never scored as pass/fail.

    `expected_tools`/`expected_region_values`/`expected_time_range` are
    None wherever there is nothing fixed to check.
    """

    name: str
    question: str
    category: str
    expect_valid_plan: bool | None
    expected_tools: frozenset[str] | None = None
    expected_region_values: tuple[str, ...] | None = None
    expected_time_range: tuple[str, str] | None = None
    min_matching_steps: int = 1


def _case(
    name: str,
    question: str,
    category: str,
    expect_valid_plan: bool | None,
    expected_tools: frozenset[str] | None = None,
    expected_region_values: tuple[str, ...] | None = None,
    expected_time_range: tuple[str, str] | None = None,
    min_matching_steps: int = 1,
) -> BenchmarkCase:
    return BenchmarkCase(
        name=name,
        question=question,
        category=category,
        expect_valid_plan=expect_valid_plan,
        expected_tools=expected_tools,
        expected_region_values=expected_region_values,
        expected_time_range=expected_time_range,
        min_matching_steps=min_matching_steps,
    )


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    _case(
        name="count_california",
        question=(
            "How many wildfires occurred in California between "
            "2024-08-01 and 2024-08-10?"
        ),
        category="count",
        expect_valid_plan=True,
        expected_tools=frozenset({"calculate_statistics"}),
        expected_region_values=("california",),
        expected_time_range=("2024-08-01", "2024-08-10"),
    ),
    _case(
        name="count_bay_area",
        question=(
            "How many fires were recorded in the Bay Area between "
            "2024-07-01 and 2024-07-15?"
        ),
        category="count",
        expect_valid_plan=True,
        expected_tools=frozenset({"calculate_statistics"}),
        expected_region_values=("bay_area",),
        expected_time_range=("2024-07-01", "2024-07-15"),
    ),
    _case(
        name="trend_daily_california",
        question=(
            "Show me the daily wildfire trend in California between "
            "2024-08-01 and 2024-08-10."
        ),
        category="trend",
        expect_valid_plan=True,
        expected_tools=frozenset({"calculate_statistics"}),
        expected_region_values=("california",),
        expected_time_range=("2024-08-01", "2024-08-10"),
    ),
    _case(
        name="trend_weekly_southern_california",
        question=(
            "What is the weekly trend of wildfires in Southern California "
            "between 2024-07-01 and 2024-08-01?"
        ),
        category="trend",
        expect_valid_plan=True,
        expected_tools=frozenset({"calculate_statistics"}),
        expected_region_values=("southern_california",),
        expected_time_range=("2024-07-01", "2024-08-01"),
    ),
    _case(
        name="compare_california_bay_area",
        question=(
            "Compare the number of wildfires in California versus the "
            "Bay Area between 2024-08-01 and 2024-08-10."
        ),
        category="compare",
        expect_valid_plan=True,
        expected_tools=frozenset({"calculate_statistics", "generate_map"}),
        expected_region_values=("california", "bay_area"),
        min_matching_steps=2,
    ),
    _case(
        name="compare_northern_central",
        question=(
            "Compare wildfire counts between Northern California and the "
            "Central Valley between 2024-06-01 and 2024-06-15."
        ),
        category="compare",
        expect_valid_plan=True,
        expected_tools=frozenset({"calculate_statistics", "generate_map"}),
        expected_region_values=("northern_california", "central_valley"),
        min_matching_steps=2,
    ),
    _case(
        name="map_california",
        question=(
            "Show me a map of wildfire counts in California between "
            "2024-08-01 and 2024-08-10."
        ),
        category="map",
        expect_valid_plan=True,
        expected_tools=frozenset({"generate_map"}),
        expected_region_values=("california",),
        expected_time_range=("2024-08-01", "2024-08-10"),
    ),
    _case(
        name="map_central_valley",
        question=(
            "Generate a wildfire map for the Central Valley between "
            "2024-07-01 and 2024-07-10."
        ),
        category="map",
        expect_valid_plan=True,
        expected_tools=frozenset({"generate_map"}),
        expected_region_values=("central_valley",),
        expected_time_range=("2024-07-01", "2024-07-10"),
    ),
    _case(
        name="forecast_california",
        question=(
            "Forecast wildfire risk in California as of "
            "2024-08-10T00:00:00Z for the next 24 hours."
        ),
        category="forecast",
        expect_valid_plan=True,
        expected_tools=frozenset({"run_forecast"}),
        expected_region_values=("california",),
    ),
    _case(
        name="forecast_southern_california",
        question=(
            "Give me a wildfire risk forecast for Southern California as "
            "of 2024-08-15T00:00:00Z."
        ),
        category="forecast",
        expect_valid_plan=True,
        expected_tools=frozenset({"run_forecast"}),
        expected_region_values=("southern_california",),
    ),
    _case(
        name="ambiguous_no_region_or_time",
        question="How many wildfires happened?",
        category="ambiguous",
        expect_valid_plan=None,
    ),
    _case(
        name="ambiguous_vague_intent",
        question="Tell me about the fire situation.",
        category="ambiguous",
        expect_valid_plan=None,
    ),
    _case(
        name="unsupported_unrelated_dataset",
        question="What is the weather forecast for tomorrow in New York City?",
        category="unsupported",
        expect_valid_plan=False,
    ),
    _case(
        name="unsupported_causal_question",
        question="Explain why California has so many wildfires.",
        category="unsupported",
        expect_valid_plan=False,
    ),
)


def _normalize_named_region_value(value: str) -> str:
    """Mirrors query.region._normalize_named's own normalization exactly."""
    return value.strip().lower().replace(" ", "_")


def _step_region_values(plan: Plan) -> set[str]:
    values: set[str] = set()

    for step in plan.steps:
        region = step.input.get("region") if isinstance(step.input, dict) else None
        if isinstance(region, dict) and isinstance(region.get("value"), str):
            values.add(_normalize_named_region_value(region["value"]))

    return values


def _step_has_exact_time_range(
    step_input: dict[str, object], expected: tuple[str, str]
) -> bool:
    time_range = step_input.get("time_range")

    if not isinstance(time_range, dict):
        return False

    return (time_range.get("start"), time_range.get("end")) == expected


@dataclass(frozen=True)
class CaseOutcome:
    """One case's scored result. `intent_correct`/`region_correct`/
    `time_correct`/`valid_plan_as_expected` are None wherever the case
    has nothing fixed to check against (see BenchmarkCase's docstring) --
    `summarize` excludes None entries from each metric's rate rather
    than counting them as failures."""

    case: BenchmarkCase
    valid_plan: bool
    error: str | None
    plan: Plan | None
    valid_plan_as_expected: bool | None
    intent_correct: bool | None
    region_correct: bool | None
    time_correct: bool | None
    execution_ok: bool


def score_case(
    case: BenchmarkCase, plan: Plan | None, error: Exception | None
) -> CaseOutcome:
    """Scores one live generate_plan() outcome against its case's fixed
    expectations. Never calls the model itself."""
    valid_plan = plan is not None

    execution_ok = valid_plan or isinstance(error, ValueError)

    valid_plan_as_expected = (
        None if case.expect_valid_plan is None else valid_plan == case.expect_valid_plan
    )

    intent_correct = None
    region_correct = None
    time_correct = None

    if valid_plan and case.expected_tools is not None:
        assert plan is not None
        matching_steps = [
            step for step in plan.steps if step.tool in case.expected_tools
        ]
        intent_correct = len(matching_steps) >= case.min_matching_steps

    if valid_plan and case.expected_region_values is not None:
        assert plan is not None
        region_values = _step_region_values(plan)
        region_correct = all(
            value in region_values for value in case.expected_region_values
        )

    if valid_plan and case.expected_time_range is not None:
        assert plan is not None
        time_correct = any(
            _step_has_exact_time_range(step.input, case.expected_time_range)
            for step in plan.steps
            if isinstance(step.input, dict)
        )

    return CaseOutcome(
        case=case,
        valid_plan=valid_plan,
        error=str(error) if error is not None else None,
        plan=plan,
        valid_plan_as_expected=valid_plan_as_expected,
        intent_correct=intent_correct,
        region_correct=region_correct,
        time_correct=time_correct,
        execution_ok=execution_ok,
    )


def _rate(flags: list[bool | None]) -> float | None:
    scored = [flag for flag in flags if flag is not None]

    return (sum(scored) / len(scored)) if scored else None


def summarize(outcomes: list[CaseOutcome]) -> dict[str, float | int | None]:
    """Six metrics, each a 0-1 rate over however many cases actually had
    that metric scored (None inputs -- cases with nothing fixed to
    check -- are excluded from a rate's denominator, not counted as
    failures)."""
    unsupported_outcomes = [
        outcome for outcome in outcomes if outcome.case.category == "unsupported"
    ]

    return {
        "total_cases": len(outcomes),
        "intent_correctness": _rate([outcome.intent_correct for outcome in outcomes]),
        "region_correctness": _rate([outcome.region_correct for outcome in outcomes]),
        "time_correctness": _rate([outcome.time_correct for outcome in outcomes]),
        "valid_plan_rate": _rate(
            [outcome.valid_plan_as_expected for outcome in outcomes]
        ),
        "execution_success": _rate([outcome.execution_ok for outcome in outcomes]),
        "unsupported_request_handling": _rate(
            [outcome.valid_plan_as_expected for outcome in unsupported_outcomes]
        ),
    }
