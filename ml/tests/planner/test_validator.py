import pytest

from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    Plan,
    PlanStep,
    validate_plan,
    validate_plan_or_raise,
)

VALID_REGION = {"kind": "named", "value": "california"}
VALID_TIME_RANGE = {"start": "2024-08-08", "end": "2024-08-15"}


def _plan(*steps: PlanStep) -> Plan:
    return Plan(question="how many fires in California last week?", steps=tuple(steps))


def test_a_valid_single_step_plan_has_no_errors():
    plan = _plan(
        PlanStep(step_id="s1", tool="resolve_region", input={"region": VALID_REGION})
    )

    assert validate_plan(plan) == []


def test_a_valid_multi_step_plan_with_a_real_dependency_has_no_errors():
    plan = _plan(
        PlanStep(
            step_id="forecast",
            tool="run_forecast",
            input={"region": VALID_REGION, "cutoff": "2024-08-15T10:00:00Z"},
        ),
        PlanStep(
            step_id="evidence",
            tool="get_result_evidence",
            input={"result_id": "$forecast.forecast_id"},
            depends_on=("forecast",),
        ),
    )

    assert validate_plan(plan) == []


def test_an_empty_plan_is_rejected():
    errors = validate_plan(Plan(question="q", steps=()))

    assert len(errors) == 1
    assert "at least one step" in errors[0]


def test_an_unknown_tool_name_is_rejected():
    plan = _plan(PlanStep(step_id="s1", tool="execute_python", input={}))

    errors = validate_plan(plan)

    assert len(errors) == 1
    assert "unknown tool" in errors[0]


def test_a_missing_required_input_field_is_rejected():
    plan = _plan(PlanStep(step_id="s1", tool="resolve_region", input={}))

    errors = validate_plan(plan)

    assert len(errors) == 1
    assert "input does not match" in errors[0]


def test_an_unsupported_operation_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": VALID_REGION,
                "time_range": VALID_TIME_RANGE,
                "operation": "compare",
            },
        )
    )

    errors = validate_plan(plan)

    assert len(errors) == 1
    assert "input does not match" in errors[0]


@pytest.mark.parametrize(
    "region",
    [
        {"kind": "bbox", "value": [10.0, 10.0, 5.0, 5.0]},  # inverted/degenerate
        {"kind": "named", "value": "atlantis"},  # not a supported name
        {"kind": "coordinates", "value": [0.0, 0.0]},  # outside the California grid
    ],
)
def test_a_semantically_invalid_region_is_rejected(region):
    plan = _plan(
        PlanStep(step_id="s1", tool="resolve_region", input={"region": region})
    )

    errors = validate_plan(plan)

    assert len(errors) == 1
    assert "invalid region" in errors[0]


def test_a_time_range_where_start_is_not_before_end_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="calculate_statistics",
            input={
                "region": VALID_REGION,
                "time_range": {"start": "2024-08-15", "end": "2024-08-08"},
                "operation": "count",
            },
        )
    )

    errors = validate_plan(plan)

    assert len(errors) == 1
    assert "invalid time_range" in errors[0]


def test_an_unparseable_cutoff_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="run_forecast",
            input={"region": VALID_REGION, "cutoff": "not-a-datetime"},
        )
    )

    errors = validate_plan(plan)

    assert len(errors) == 1
    assert "cutoff" in errors[0]


def test_a_duplicate_step_id_is_rejected():
    plan = _plan(
        PlanStep(step_id="s1", tool="resolve_region", input={"region": VALID_REGION}),
        PlanStep(step_id="s1", tool="resolve_region", input={"region": VALID_REGION}),
    )

    errors = validate_plan(plan)

    assert any("duplicate step_id" in error for error in errors)


def test_depends_on_referencing_an_unknown_step_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="resolve_region",
            input={"region": VALID_REGION},
            depends_on=("does-not-exist",),
        )
    )

    errors = validate_plan(plan)

    assert any("depends_on references unknown step" in error for error in errors)


def test_depends_on_a_later_step_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="resolve_region",
            input={"region": VALID_REGION},
            depends_on=("s2",),
        ),
        PlanStep(step_id="s2", tool="resolve_region", input={"region": VALID_REGION}),
    )

    errors = validate_plan(plan)

    assert any("does not come before it" in error for error in errors)


def test_a_step_ref_to_an_unknown_step_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="s1",
            tool="get_result_evidence",
            input={"result_id": "$does-not-exist.forecast_id"},
        )
    )

    errors = validate_plan(plan)

    assert any("references unknown step" in error for error in errors)


def test_a_step_ref_not_declared_in_depends_on_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="forecast",
            tool="run_forecast",
            input={"region": VALID_REGION, "cutoff": "2024-08-15T10:00:00Z"},
        ),
        PlanStep(
            step_id="evidence",
            tool="get_result_evidence",
            input={"result_id": "$forecast.forecast_id"},
            # depends_on left empty -- the reference above is undeclared.
        ),
    )

    errors = validate_plan(plan)

    assert any("without declaring it in depends_on" in error for error in errors)


def test_a_step_ref_to_a_field_the_tool_does_not_produce_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="forecast",
            tool="run_forecast",
            input={"region": VALID_REGION, "cutoff": "2024-08-15T10:00:00Z"},
        ),
        PlanStep(
            step_id="evidence",
            tool="get_result_evidence",
            input={"result_id": "$forecast.bogus_field"},
            depends_on=("forecast",),
        ),
    )

    errors = validate_plan(plan)

    assert any("only produces" in error for error in errors)


def test_a_step_ref_to_a_later_or_self_step_is_rejected():
    plan = _plan(
        PlanStep(
            step_id="evidence",
            tool="get_result_evidence",
            input={"result_id": "$forecast.forecast_id"},
            depends_on=("forecast",),
        ),
        PlanStep(
            step_id="forecast",
            tool="run_forecast",
            input={"region": VALID_REGION, "cutoff": "2024-08-15T10:00:00Z"},
        ),
    )

    errors = validate_plan(plan)

    assert any("does not come before it" in error for error in errors)


def test_validate_plan_or_raise_does_nothing_for_a_valid_plan():
    plan = _plan(
        PlanStep(step_id="s1", tool="resolve_region", input={"region": VALID_REGION})
    )

    validate_plan_or_raise(plan)  # must not raise


def test_validate_plan_or_raise_raises_for_an_invalid_plan():
    plan = _plan(PlanStep(step_id="s1", tool="execute_python", input={}))

    with pytest.raises(ValueError, match="unknown tool"):
        validate_plan_or_raise(plan)
