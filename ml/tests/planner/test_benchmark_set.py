from ai_earth_intelligence_and_forecasting_engine.planner.benchmark_set import (
    BENCHMARK_CASES,
    CATEGORIES,
    score_case,
    summarize,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    Plan,
    PlanStep,
)


def _plan(*steps: PlanStep, question: str = "q") -> Plan:
    return Plan(question=question, steps=tuple(steps))


def test_benchmark_cases_cover_every_category():
    assert {case.category for case in BENCHMARK_CASES} == set(CATEGORIES)


def test_benchmark_case_names_are_unique():
    names = [case.name for case in BENCHMARK_CASES]

    assert len(names) == len(set(names))


def test_score_case_matches_a_correct_single_tool_plan():
    case = next(c for c in BENCHMARK_CASES if c.name == "count_california")
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        )
    )

    outcome = score_case(case, plan, None)

    assert outcome.valid_plan is True
    assert outcome.valid_plan_as_expected is True
    assert outcome.intent_correct is True
    assert outcome.region_correct is True
    assert outcome.time_correct is True
    assert outcome.execution_ok is True


def test_score_case_flags_wrong_tool_as_intent_incorrect():
    case = next(c for c in BENCHMARK_CASES if c.name == "map_california")
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        )
    )

    outcome = score_case(case, plan, None)

    assert outcome.intent_correct is False


def test_score_case_region_check_tolerates_the_same_casing_the_real_validator_does():
    # query.region._normalize_named lowercases and underscores named
    # region values before matching ("Bay Area" -> "bay_area"), so a
    # plan using human-readable casing is just as valid as one using the
    # exact NAMED_REGIONS key -- region correctness must accept both.
    case = next(c for c in BENCHMARK_CASES if c.name == "count_bay_area")
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "Bay Area"},
                "time_range": {"start": "2024-07-01", "end": "2024-07-15"},
                "operation": "count",
            },
        )
    )

    outcome = score_case(case, plan, None)

    assert outcome.region_correct is True


def test_score_case_flags_wrong_region_as_region_incorrect():
    case = next(c for c in BENCHMARK_CASES if c.name == "count_bay_area")
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-07-01", "end": "2024-07-15"},
                "operation": "count",
            },
        )
    )

    outcome = score_case(case, plan, None)

    assert outcome.region_correct is False


def test_score_case_flags_wrong_time_range_as_time_incorrect():
    case = next(c for c in BENCHMARK_CASES if c.name == "count_california")
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2020-01-01", "end": "2020-01-02"},
                "operation": "count",
            },
        )
    )

    outcome = score_case(case, plan, None)

    assert outcome.time_correct is False


def test_score_case_compare_requires_min_matching_steps():
    case = next(c for c in BENCHMARK_CASES if c.name == "compare_california_bay_area")
    one_region_plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        )
    )
    two_region_plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        ),
        PlanStep(
            step_id="s2",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "bay_area"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        ),
    )

    assert score_case(case, one_region_plan, None).intent_correct is False
    assert score_case(case, one_region_plan, None).region_correct is False

    two_region_outcome = score_case(case, two_region_plan, None)
    assert two_region_outcome.intent_correct is True
    assert two_region_outcome.region_correct is True


def test_score_case_unsupported_rejected_as_expected():
    case = next(c for c in BENCHMARK_CASES if c.name == "unsupported_causal_question")

    outcome = score_case(case, None, ValueError("unknown tool"))

    assert outcome.valid_plan is False
    assert outcome.valid_plan_as_expected is True
    assert outcome.execution_ok is True


def test_score_case_unsupported_but_a_plan_was_produced_anyway_is_a_miss():
    case = next(c for c in BENCHMARK_CASES if c.name == "unsupported_causal_question")
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        )
    )

    outcome = score_case(case, plan, None)

    assert outcome.valid_plan_as_expected is False


def test_score_case_ambiguous_case_is_never_scored_pass_or_fail():
    case = next(c for c in BENCHMARK_CASES if c.name == "ambiguous_no_region_or_time")

    rejected = score_case(case, None, ValueError("missing region"))
    accepted = score_case(
        case,
        _plan(
            PlanStep(
                step_id="s1",
                tool="calculate_statistics",
                input={
                    "region": {"kind": "named", "value": "california"},
                    "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                    "operation": "count",
                },
            )
        ),
        None,
    )

    assert rejected.valid_plan_as_expected is None
    assert accepted.valid_plan_as_expected is None


def test_score_case_a_non_valueerror_failure_is_not_execution_ok():
    case = next(c for c in BENCHMARK_CASES if c.name == "count_california")

    outcome = score_case(case, None, TimeoutError("network timed out"))

    assert outcome.execution_ok is False


def test_summarize_computes_rates_excluding_not_applicable_cases():
    passing_case = next(c for c in BENCHMARK_CASES if c.name == "count_california")
    ambiguous_case = next(
        c for c in BENCHMARK_CASES if c.name == "ambiguous_no_region_or_time"
    )
    good_plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        )
    )

    outcomes = [
        score_case(passing_case, good_plan, None),
        score_case(ambiguous_case, None, ValueError("missing region")),
    ]

    summary = summarize(outcomes)

    assert summary["total_cases"] == 2
    # The ambiguous case contributes None to every per-metric rate, so
    # each rate is computed over the one applicable case only.
    assert summary["intent_correctness"] == 1.0
    assert summary["region_correctness"] == 1.0
    assert summary["time_correctness"] == 1.0
    assert summary["valid_plan_rate"] == 1.0
    assert summary["execution_success"] == 1.0
    assert summary["unsupported_request_handling"] is None
