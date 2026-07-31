import pytest

from ai_earth_intelligence_and_forecasting_engine.planner.generate_answer import (
    RESULT_CATEGORY_BY_TOOL,
    StepResult,
    _assemble_facts,
    _build_answer_prompt,
    generate_answer,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    Plan,
    PlanStep,
)
from ai_earth_intelligence_and_forecasting_engine.query.evidence import (
    build_evidence,
    evidence_to_dict,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    RegionSpec,
    TimeRangeSpec,
)
from ai_earth_intelligence_and_forecasting_engine.query.statistics import count
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeBeta:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


class _FakeClient:
    def __init__(self, response):
        self.beta = _FakeBeta(response)


class _MustNotBeCalledClient:
    """Fails the test if the model is ever actually invoked."""

    class _Messages:
        def create(self, **kwargs):
            raise AssertionError("the model must not be called when there are no facts")

    class _Beta:
        def __init__(self):
            self.messages = _MustNotBeCalledClient._Messages()

    def __init__(self):
        self.beta = _MustNotBeCalledClient._Beta()


def _real_count_fact():
    """Builds a genuine StepResult/evidence pair using the real Task
    2.4/2.6 functions, not a hand-typed fixture -- proving generate_answer
    works against the actual shapes those functions produce."""
    region = normalize_region(RegionSpec(kind="named", value="california"))
    time_range = normalize_time_range(
        TimeRangeSpec(start="2024-08-08", end="2024-08-15")
    )
    real_count = count([], region, time_range)
    evidence = build_evidence(
        dataset="NASA_FIRMS:VIIRS_SNPP_SP",
        region=region,
        time_range=time_range,
        query_parameters={"operation": "count"},
    )

    step = PlanStep(
        step_id="s1",
        tool="calculate_statistics",
        input={
            "region": {"kind": "named", "value": "california"},
            "time_range": {"start": "2024-08-08", "end": "2024-08-15"},
            "operation": "count",
        },
    )
    result = StepResult(
        step_id="s1",
        tool="calculate_statistics",
        result={"count": real_count},
        evidence=evidence_to_dict(evidence),
    )

    return step, result


def test_result_category_by_tool_only_covers_fact_producing_tools():
    # resolve_region resolves geometry (not a fact); get_result_evidence
    # fetches metadata about a fact another step already produced.
    assert set(RESULT_CATEGORY_BY_TOOL.keys()) == {
        "get_data",
        "calculate_statistics",
        "generate_map",
        "run_forecast",
    }
    assert RESULT_CATEGORY_BY_TOOL["calculate_statistics"] == "computed"
    assert RESULT_CATEGORY_BY_TOOL["generate_map"] == "computed"
    assert RESULT_CATEGORY_BY_TOOL["run_forecast"] == "predicted"
    assert RESULT_CATEGORY_BY_TOOL["get_data"] == "observed"


def test_assemble_facts_builds_a_fact_from_a_real_computed_result():
    step, result = _real_count_fact()
    plan = Plan(question="how many fires in California last week?", steps=(step,))

    facts = _assemble_facts(plan, {"s1": result})

    assert len(facts) == 1
    assert facts[0].category == "computed"
    assert facts[0].result == {"count": 0}
    assert facts[0].evidence["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"


def test_assemble_facts_skips_a_step_whose_tool_produces_no_fact():
    step = PlanStep(
        step_id="s1",
        tool="resolve_region",
        input={"region": {"kind": "named", "value": "california"}},
    )
    result = StepResult(
        step_id="s1", tool="resolve_region", result={"bbox": [1, 2, 3, 4]}
    )
    plan = Plan(question="q", steps=(step,))

    assert _assemble_facts(plan, {"s1": result}) == ()


def test_assemble_facts_skips_a_step_with_no_result_at_all():
    step, _ = _real_count_fact()
    plan = Plan(question="q", steps=(step,))

    assert _assemble_facts(plan, {}) == ()


def test_build_answer_prompt_includes_the_question_and_tagged_facts():
    step, result = _real_count_fact()
    plan = Plan(question="how many fires in California last week?", steps=(step,))
    facts = _assemble_facts(plan, {"s1": result})

    prompt = _build_answer_prompt(plan.question, facts)

    assert "how many fires in California last week?" in prompt
    assert "[computed]" in prompt
    assert '"count": 0' in prompt


def test_generate_answer_returns_the_no_facts_summary_without_calling_the_model():
    plan = Plan(question="q", steps=())

    answer = generate_answer(plan, {}, _MustNotBeCalledClient())

    assert answer.facts == ()
    assert "No executed results" in answer.summary


def test_generate_answer_produces_a_grounded_answer_with_real_computed_facts():
    step, result = _real_count_fact()
    plan = Plan(question="how many fires in California last week?", steps=(step,))
    text_block = _FakeTextBlock("0 fires occurred (computed).")
    client = _FakeClient(_FakeResponse(content=[text_block]))

    answer = generate_answer(plan, {"s1": result}, client)

    assert answer.question == plan.question
    assert len(answer.facts) == 1
    assert answer.facts[0].category == "computed"
    assert answer.summary == "0 fires occurred (computed)."

    sent = client.beta.messages.last_kwargs
    assert sent["model"] == "claude-opus-5"


def test_generate_answer_raises_on_refusal():
    step, result = _real_count_fact()
    plan = Plan(question="q", steps=(step,))
    response = _FakeResponse(content=[], stop_reason="refusal", stop_details="blocked")
    client = _FakeClient(response)

    with pytest.raises(ValueError, match="refused"):
        generate_answer(plan, {"s1": result}, client)


def test_generate_answer_raises_when_no_text_block_is_present():
    step, result = _real_count_fact()
    plan = Plan(question="q", steps=(step,))
    client = _FakeClient(_FakeResponse(content=[]))

    with pytest.raises(ValueError, match="no text"):
        generate_answer(plan, {"s1": result}, client)
