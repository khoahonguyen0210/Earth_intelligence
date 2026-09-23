import json

import pytest

from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    run_analysis,
)

SAMPLE_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence\n"
    "37.5,-119.5,2024-08-01,1000,n\n"
    "37.6,-119.6,2024-08-01,1400,h\n"
    "37.5,-119.5,2024-08-02,0900,n\n"
    "0.0,0.0,2024-08-01,1000,n\n"  # outside California, excluded
)


@pytest.fixture
def firms_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "test-key")

    path = tmp_path / "firms_sample.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")

    return path


def _payload(**overrides):
    base = {
        "question": "How many fires in California from Aug 1-2, 2024?",
        "intent": "count",
        "region": {"kind": "named", "value": "california"},
        "time_range": {"start": "2024-08-01", "end": "2024-08-02"},
        "operation": "count",
    }
    base.update(overrides)
    return base


def test_run_analysis_count(firms_csv):
    response = run_analysis(_payload(), firms_csv)

    assert response["result"] == {"count": 3}
    assert response["evidence"]["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"
    assert response["evidence"]["region_label"] == "california"

    json.dumps(response)


def test_run_analysis_daily_aggregate(firms_csv):
    response = run_analysis(
        _payload(intent="aggregate", operation="daily_aggregate"), firms_csv
    )

    daily = {entry["date"]: entry["count"] for entry in response["result"]["daily"]}

    assert daily["2024-08-01"] == 2
    assert daily["2024-08-02"] == 1


def test_run_analysis_weekly_aggregate(firms_csv):
    response = run_analysis(
        _payload(intent="aggregate", operation="weekly_aggregate"), firms_csv
    )

    assert sum(entry["count"] for entry in response["result"]["weekly"]) == 3


def test_run_analysis_map(firms_csv):
    response = run_analysis(_payload(intent="map", operation="map"), firms_csv)

    assert response["result"]["type"] == "FeatureCollection"
    assert response["result"]["features"][0]["properties"]["value"] == 3
    assert response["result"]["features"][0]["properties"]["units"] == "fire_count"


def test_run_analysis_rejects_unsupported_operation(firms_csv):
    with pytest.raises(ValueError, match="Unsupported operation"):
        run_analysis(_payload(operation="forecast"), firms_csv)


def test_run_analysis_rejects_empty_question(firms_csv):
    with pytest.raises(ValueError, match="question must not be empty"):
        run_analysis(_payload(question="   "), firms_csv)


def test_run_analysis_rejects_invalid_intent(firms_csv):
    with pytest.raises(ValueError):
        run_analysis(_payload(intent="summarize"), firms_csv)


def test_run_analysis_output_is_json_serializable(firms_csv):
    response = run_analysis(_payload(), firms_csv)

    json.dumps(response)


def test_run_analysis_over_history_refuses_a_period_the_history_does_not_cover(
    tmp_path,
):
    # Only Aug 1-5 2024 downloaded: asking about Aug 1-10 must be refused,
    # never answered as if Aug 6-10 had zero fires.
    (tmp_path / "VIIRS_SNPP_SP_2024-08-01_5d.csv").write_text(
        "latitude,longitude,acq_date,acq_time\n", encoding="utf-8"
    )
    payload = _payload()
    payload["time_range"] = {"start": "2024-08-01", "end": "2024-08-10"}

    with pytest.raises(ValueError, match="no real FIRMS fire history"):
        run_analysis(payload, tmp_path)


def test_run_analysis_over_history_counts_across_span_files(tmp_path):
    header = "latitude,longitude,acq_date,acq_time,confidence\n"
    (tmp_path / "VIIRS_SNPP_SP_2024-08-01_5d.csv").write_text(
        header + "37.5,-119.5,2024-08-02,1000,n\n37.6,-119.6,2024-08-05,2300,n\n",
        encoding="utf-8",
    )
    (tmp_path / "VIIRS_SNPP_SP_2024-08-06_5d.csv").write_text(
        header + "37.5,-119.5,2024-08-06,0100,h\n", encoding="utf-8"
    )
    payload = _payload()
    payload["time_range"] = {"start": "2024-08-01", "end": "2024-08-10"}

    response = run_analysis(payload, tmp_path)

    assert response["result"] == {"count": 3}
