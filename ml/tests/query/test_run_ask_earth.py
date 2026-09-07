"""Task 14.1: run_ask_earth end to end -- a real question, a real
(faked-at-the-API-boundary) planner call, real dispatch against a real
FIRMS fixture, and a real (faked) answer call. Only the two Gemini calls
are faked (the same pattern tests/planner/test_generate_plan.py and
test_generate_answer.py already use); everything else -- the validator,
the dispatcher, the analysis pipeline -- is the real code."""

import json

import pytest

from ai_earth_intelligence_and_forecasting_engine.query import dispatch
from ai_earth_intelligence_and_forecasting_engine.query.dispatch import Backend
from ai_earth_intelligence_and_forecasting_engine.query.run_ask_earth import (
    run_ask_earth,
)

SAMPLE_FIRMS_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence\n"
    "37.5,-119.5,2024-08-01,1000,n\n"
    "37.6,-119.6,2024-08-01,1400,h\n"
)


@pytest.fixture
def firms_history(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "test-key")
    path = tmp_path / "firms_sample.csv"
    path.write_text(SAMPLE_FIRMS_CSV, encoding="utf-8")
    monkeypatch.setattr(dispatch, "DEFAULT_FIRMS_HISTORY_DIR", path)
    return path


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
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


def _plan_response(steps):
    return _FakeResponse(text=json.dumps({"steps": steps}))


def test_run_ask_earth_a_count_question_end_to_end(firms_history):
    plan_payload = [
        {
            "step_id": "count",
            "tool": "calculate_statistics",
            "input": {
                "region": {"kind": "named", "value": "california"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-02"},
                "operation": "count",
            },
            "depends_on": [],
        }
    ]
    client = _FakeClient(
        [
            _plan_response(plan_payload),
            _FakeResponse(text="There were 2 fires (observed)."),
        ]
    )
    backend = Backend(base_url="http://backend.test")

    response = run_ask_earth(
        {"question": "How many fires in California on Aug 1-2, 2024?"}, client, backend
    )

    assert response["question"] == "How many fires in California on Aug 1-2, 2024?"
    assert response["answer"] == "There were 2 fires (observed)."
    assert response["outputs"]["count"]["count"] == 2
    assert len(response["facts"]) == 1
    fact = response["facts"][0]
    assert fact["step_id"] == "count"
    assert fact["category"] == "computed"
    assert fact["result"] == {"count": 2}
    assert fact["evidence"]["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"
    assert response["plan"]["steps"][0]["tool"] == "calculate_statistics"
    json.dumps(response)  # the whole thing must be JSON-serializable end to end

    # Both real LLM calls happened, in order: plan, then answer.
    assert len(client.models.calls) == 2
    assert (
        "response_schema" in client.models.calls[0]["config"]
    )  # generate_plan's structured output
    assert (
        "response_schema" not in client.models.calls[1]["config"]
    )  # generate_answer is free text


def test_run_ask_earth_raises_when_the_plan_fails_validation(firms_history):
    # An unknown tool: generate_plan's own validate_plan_or_raise call
    # rejects this before run_ask_earth's dispatch is ever reached.
    plan_payload = [
        {"step_id": "s1", "tool": "delete_everything", "input": {}, "depends_on": []}
    ]
    client = _FakeClient([_plan_response(plan_payload)])
    backend = Backend(base_url="http://backend.test")

    with pytest.raises(ValueError, match="unknown tool"):
        run_ask_earth({"question": "anything"}, client, backend)

    assert len(client.models.calls) == 1  # never reached the answer call


def test_run_ask_earth_raises_when_a_step_fails(firms_history):
    # A named region the deterministic validator itself rejects (Task
    # 7.2 already checks region validity against the real normalize_region).
    plan_payload = [
        {
            "step_id": "count",
            "tool": "calculate_statistics",
            "input": {
                "region": {"kind": "named", "value": "atlantis"},
                "time_range": {"start": "2024-08-01", "end": "2024-08-02"},
                "operation": "count",
            },
            "depends_on": [],
        }
    ]
    client = _FakeClient([_plan_response(plan_payload)])
    backend = Backend(base_url="http://backend.test")

    with pytest.raises(ValueError, match="invalid region"):
        run_ask_earth({"question": "fires in atlantis?"}, client, backend)
