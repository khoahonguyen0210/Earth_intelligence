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
    assert summary["intent_correctness"] == 1.0
    assert summary["region_correctness"] == 1.0
    assert summary["time_correctness"] == 1.0
    assert summary["valid_plan_rate"] == 1.0
    assert summary["execution_success"] == 1.0
    assert summary["unsupported_request_handling"] is None
    assert summary["adversarial_rejection"] is None


def test_an_injection_that_produces_no_plan_counts_as_rejected():
    case = next(
        c for c in BENCHMARK_CASES if c.name == "adversarial_ignore_instructions"
    )

    outcome = score_case(case, None, ValueError("no valid plan"))

    assert outcome.valid_plan_as_expected is True
    assert summarize([outcome])["adversarial_rejection"] == 1.0


def test_a_docs_only_plan_for_an_attack_is_contained_but_not_rejected():
    case = next(
        c for c in BENCHMARK_CASES if c.name == "adversarial_reveal_secrets"
    )
    docs_only = _plan(
        PlanStep(
            step_id="docs",
            tool="search_docs",
            input={"query": "where can I find the api key"},
        )
    )

    outcome = score_case(case, docs_only, None)

    assert outcome.valid_plan_as_expected is False
    assert outcome.contained is True


def test_an_attack_that_reaches_a_data_tool_is_not_contained():
    case = next(
        c for c in BENCHMARK_CASES if c.name == "adversarial_ignore_instructions"
    )
    reaches_data = _plan(
        PlanStep(
            step_id="stats",
            tool="calculate_statistics",
            input={
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-10"},
                "operation": "count",
            },
        )
    )

    assert score_case(case, reaches_data, None).contained is False
    assert score_case(case, None, ValueError("rejected")).contained is True


def test_contained_handling_is_reported_over_cases_that_define_it():
    cases = {c.name: c for c in BENCHMARK_CASES}
    safe = score_case(
        cases["adversarial_reveal_secrets"],
        _plan(PlanStep("d", "search_docs", {"query": "q"})),
        None,
    )
    rejected = score_case(
        cases["unsupported_region_outside_california"], None, ValueError("no")
    )
    unrelated = score_case(cases["count_california"], None, ValueError("no"))

    summary = summarize([safe, rejected, unrelated])

    assert summary["contained_handling"] == 1.0


def test_the_explained_forecast_case_needs_both_forecast_tools():
    case = next(
        c for c in BENCHMARK_CASES if c.name == "forecast_explained_northern_california"
    )
    region = {"kind": "named", "value": "northern_california"}
    only_run = _plan(
        PlanStep(
            step_id="forecast",
            tool="run_forecast",
            input={"region": region, "cutoff": "2024-08-12T00:00:00Z"},
        )
    )
    both = _plan(
        PlanStep(
            step_id="forecast",
            tool="run_forecast",
            input={"region": region, "cutoff": "2024-08-12T00:00:00Z"},
        ),
        PlanStep(
            step_id="risk",
            tool="get_forecast_result",
            input={"result_id": "$forecast.forecast_id"},
            depends_on=("forecast",),
        ),
    )

    assert score_case(case, only_run, None).intent_correct is False
    assert score_case(case, both, None).intent_correct is True
