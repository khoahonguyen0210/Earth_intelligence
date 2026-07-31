import json

import pytest

from ai_earth_intelligence_and_forecasting_engine.planner.generate_plan import (
    _SYSTEM_PROMPT,
    PLAN_OUTPUT_SCHEMA,
    generate_plan,
    parse_plan,
)
from ai_earth_intelligence_and_forecasting_engine.planner.tools import TOOL_NAMES


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


def _valid_plan_payload():
    return {
        "steps": [
            {
                "step_id": "s1",
                "tool": "resolve_region",
                "input": {"region": {"kind": "named", "value": "california"}},
                "depends_on": [],
            },
        ]
    }


def test_plan_output_schema_tool_enum_matches_tool_names():
    step_schema = PLAN_OUTPUT_SCHEMA["properties"]["steps"]["items"]
    tool_property = step_schema["properties"]["tool"]

    assert set(tool_property["enum"]) == TOOL_NAMES


def test_system_prompt_mentions_every_tool_name():
    for name in TOOL_NAMES:
        assert name in _SYSTEM_PROMPT


def test_parse_plan_builds_the_expected_plan():
    payload = {
        "steps": [
            {
                "step_id": "a",
                "tool": "resolve_region",
                "input": {"region": {"kind": "named", "value": "california"}},
                "depends_on": [],
            },
            {
                "step_id": "b",
                "tool": "get_result_evidence",
                "input": {"result_id": "$a.bbox"},
                "depends_on": ["a"],
            },
        ]
    }

    plan = parse_plan("how many fires in California?", payload)

    assert plan.question == "how many fires in California?"
    assert len(plan.steps) == 2
    assert plan.steps[0].step_id == "a"
    assert plan.steps[0].depends_on == ()
    assert plan.steps[1].depends_on == ("a",)


def test_generate_plan_returns_a_validated_plan_on_success():
    text_block = _FakeTextBlock(json.dumps(_valid_plan_payload()))
    client = _FakeClient(_FakeResponse(content=[text_block]))

    plan = generate_plan("how many fires in California?", client)

    assert plan.question == "how many fires in California?"
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "resolve_region"


def test_generate_plan_sends_the_question_and_the_plan_schema():
    text_block = _FakeTextBlock(json.dumps(_valid_plan_payload()))
    client = _FakeClient(_FakeResponse(content=[text_block]))

    generate_plan("what is the fire count?", client)

    sent = client.beta.messages.last_kwargs
    assert sent["model"] == "claude-opus-5"
    assert sent["messages"] == [{"role": "user", "content": "what is the fire count?"}]
    assert sent["output_config"]["format"]["schema"] == PLAN_OUTPUT_SCHEMA


def test_generate_plan_raises_when_the_llm_produces_an_invalid_plan():
    invalid_step = {
        "step_id": "s1", "tool": "execute_python", "input": {}, "depends_on": []
    }
    text_block = _FakeTextBlock(json.dumps({"steps": [invalid_step]}))
    client = _FakeClient(_FakeResponse(content=[text_block]))

    with pytest.raises(ValueError, match="unknown tool"):
        generate_plan("do something unsupported", client)


def test_generate_plan_raises_on_refusal():
    response = _FakeResponse(content=[], stop_reason="refusal", stop_details="blocked")
    client = _FakeClient(response)

    with pytest.raises(ValueError, match="refused"):
        generate_plan("a disallowed question", client)


def test_generate_plan_raises_when_no_text_block_is_present():
    response = _FakeResponse(content=[])
    client = _FakeClient(response)

    with pytest.raises(ValueError, match="no text"):
        generate_plan("q", client)
