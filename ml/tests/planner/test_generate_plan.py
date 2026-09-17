import json

import pytest

from ai_earth_intelligence_and_forecasting_engine.planner.generate_plan import (
    _GEMINI_PLAN_SCHEMA,
    _SYSTEM_PROMPT,
    PLAN_OUTPUT_SCHEMA,
    _to_gemini_schema,
    generate_plan,
    parse_plan,
)
from ai_earth_intelligence_and_forecasting_engine.planner.tools import TOOL_NAMES
from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    MAX_QUESTION_CHARS,
)


class _FakeResponse:
    def __init__(self, text=None, raises=None):
        self._text = text
        self._raises = raises

    @property
    def text(self):
        if self._raises is not None:
            raise self._raises
        return self._text


class _FakeModels:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


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
    text = json.dumps(_valid_plan_payload())
    client = _FakeClient(_FakeResponse(text=text))

    plan = generate_plan("how many fires in California?", client)

    assert plan.question == "how many fires in California?"
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "resolve_region"


def test_generate_plan_sends_the_question_and_the_plan_schema():
    text = json.dumps(_valid_plan_payload())
    client = _FakeClient(_FakeResponse(text=text))

    generate_plan("what is the fire count?", client)

    sent = client.models.last_kwargs
    assert sent["model"] == "gemini-3.1-flash-lite"
    assert sent["contents"] == "what is the fire count?"
    assert sent["config"]["system_instruction"] == _SYSTEM_PROMPT
    assert sent["config"]["response_schema"] == _GEMINI_PLAN_SCHEMA


def test_to_gemini_schema_strips_additional_properties_recursively():
    schema = _to_gemini_schema(PLAN_OUTPUT_SCHEMA)

    assert "additionalProperties" not in schema
    assert "additionalProperties" not in schema["properties"]["steps"]["items"]


def test_gemini_plan_schema_gives_input_a_real_per_tool_union_schema():
    input_schema = _GEMINI_PLAN_SCHEMA["properties"]["steps"]["items"]["properties"][
        "input"
    ]

    assert set(input_schema.keys()) == {"anyOf"}
    assert len(input_schema["anyOf"]) == len(TOOL_NAMES)
    assert all(
        "additionalProperties" not in variant for variant in input_schema["anyOf"]
    )


def test_generate_plan_raises_when_the_llm_produces_an_invalid_plan():
    invalid_step = {
        "step_id": "s1", "tool": "execute_python", "input": {}, "depends_on": []
    }
    text = json.dumps({"steps": [invalid_step]})
    client = _FakeClient(_FakeResponse(text=text))

    with pytest.raises(ValueError, match="unknown tool"):
        generate_plan("do something unsupported", client)


def test_generate_plan_raises_on_refusal():
    client = _FakeClient(_FakeResponse(raises=ValueError("blocked by safety filter")))

    with pytest.raises(ValueError, match="refused"):
        generate_plan("a disallowed question", client)


def test_generate_plan_raises_when_no_text_block_is_present():
    client = _FakeClient(_FakeResponse(text=""))

    with pytest.raises(ValueError, match="no text"):
        generate_plan("q", client)


def test_an_overlong_question_is_refused_before_the_model_is_called():
    client = _FakeClient(_FakeResponse(text=json.dumps(_valid_plan_payload())))

    with pytest.raises(ValueError, match="question exceeds"):
        generate_plan("q" * (MAX_QUESTION_CHARS + 1), client)

    assert client.models.last_kwargs is None, "no model call for a refused question"
