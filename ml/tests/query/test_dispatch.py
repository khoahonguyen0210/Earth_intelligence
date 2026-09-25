"""dispatch.py wires the planner tools to real,
already-existing computation. Each dispatch_* test proves the real
function actually ran (a real count, a real bbox, a real evidence
record), not that some object was returned."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pytest
import requests
import xarray as xr

from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    Plan,
    PlanStep,
)
from ai_earth_intelligence_and_forecasting_engine.query import dispatch
from ai_earth_intelligence_and_forecasting_engine.query.dispatch import (
    Backend,
    StepFailed,
    dispatch_calculate_statistics,
    dispatch_generate_map,
    dispatch_get_data,
    dispatch_get_forecast_result,
    dispatch_get_result_evidence,
    dispatch_resolve_region,
    dispatch_run_forecast,
    execute_plan,
)

SAMPLE_FIRMS_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence\n"
    "37.5,-119.5,2024-08-01,1000,n\n"
    "37.6,-119.6,2024-08-01,1400,h\n"
    "37.5,-119.5,2024-08-02,0900,n\n"
    "0.0,0.0,2024-08-01,1000,n\n"  # outside California, excluded by region filtering
)

NAMED_CALIFORNIA = {"kind": "named", "value": "california"}
AUGUST_2024 = {"start": "2024-08-01", "end": "2024-08-02"}


@pytest.fixture
def firms_history(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "test-key")
    path = tmp_path / "firms_sample.csv"
    path.write_text(SAMPLE_FIRMS_CSV, encoding="utf-8")
    monkeypatch.setattr(dispatch, "DEFAULT_FIRMS_HISTORY_DIR", path)
    return path


@pytest.fixture
def era5_history(tmp_path, monkeypatch):
    history_dir = tmp_path / "era5"
    history_dir.mkdir()
    cutoff = datetime(2024, 8, 15, 10, tzinfo=timezone.utc)

    dataset = xr.Dataset(
        {
            "t2m": (
                ["valid_time", "latitude", "longitude"],
                np.array([[[295.0, 296.0]]]),
            ),
            "tp": (
                ["valid_time", "latitude", "longitude"],
                np.array([[[0.001, 0.001]]]),
            ),
            "u10": (["valid_time", "latitude", "longitude"], np.array([[[1.0, 1.0]]])),
            "v10": (["valid_time", "latitude", "longitude"], np.array([[[1.0, 1.0]]])),
            "d2m": (
                ["valid_time", "latitude", "longitude"],
                np.array([[[289.0, 289.0]]]),
            ),
        },
        coords={
            "valid_time": [np.datetime64("2024-08-15T10:00:00")],
            "latitude": [37.5],
            "longitude": [-119.5, 10.0],
        },
    )
    dataset.to_netcdf(history_dir / "era5_land_2024_08.nc")
    dataset.close()

    monkeypatch.setattr(dispatch, "DEFAULT_ERA5_HISTORY_DIR", history_dir)
    return cutoff


def test_dispatch_resolve_region_returns_the_real_california_bbox():
    output = dispatch_resolve_region({"region": NAMED_CALIFORNIA})

    assert output["source_kind"] == "named"
    assert output["label"] == "california"
    assert output["bbox"][0] < output["bbox"][2]  # west < east, a real bbox
    json.dumps(output)  # must be JSON-serializable, like every other tool output


def test_dispatch_get_data_firms_counts_only_records_inside_the_region(firms_history):
    output = dispatch_get_data(
        {"dataset": "firms", "region": NAMED_CALIFORNIA, "time_range": AUGUST_2024}
    )

    assert output["source"] == "NASA_FIRMS"
    assert output["record_count"] == 3  # the fourth row (0,0) is outside California
    assert output["provenance"]["source"] == "NASA_FIRMS"
    assert (
        output["provenance"]["checksum"] is None
    )  # no single raw file backs a directory read


def test_dispatch_get_data_era5_land_counts_only_records_inside_the_bbox(era5_history):
    cutoff = era5_history
    output = dispatch_get_data(
        {
            "dataset": "era5_land",
            "region": {"kind": "bbox", "value": [-120.0, 37.0, -119.0, 38.0]},
            "time_range": {"start": "2024-08-01", "end": cutoff.isoformat()},
        }
    )

    assert output["source"] == "ERA5-Land"
    assert output["record_count"] == 1  # only the -119.5 point falls in the bbox
    assert output["provenance"]["source"] == "ERA5-Land"


def test_dispatch_get_data_rejects_an_unknown_dataset():
    with pytest.raises(ValueError, match="Unsupported dataset"):
        dispatch_get_data(
            {
                "dataset": "static_geography",
                "region": NAMED_CALIFORNIA,
                "time_range": AUGUST_2024,
            }
        )


def test_dispatch_calculate_statistics_runs_the_real_analysis_pipeline(firms_history):
    result, evidence = dispatch_calculate_statistics(
        "how many fires in California?",
        {"region": NAMED_CALIFORNIA, "time_range": AUGUST_2024, "operation": "count"},
    )

    assert result["count"] == 3
    assert evidence["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"
    assert evidence["query_parameters"]["question"] == "how many fires in California?"


def test_dispatch_generate_map_returns_a_real_feature_collection(firms_history):
    result, evidence = dispatch_generate_map(
        "map fires in California",
        {"region": NAMED_CALIFORNIA, "time_range": AUGUST_2024},
    )

    assert result["type"] == "FeatureCollection"
    assert result["features"][0]["properties"]["value"] == 3
    assert evidence["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"


def _response(status_code: int, body: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body).encode("utf-8")
    response.headers["content-type"] = "application/json"
    return response


def test_dispatch_run_forecast_polls_until_succeeded():
    backend = Backend(base_url="http://backend.test", poll_interval_seconds=0)
    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.post"
        ) as mock_post,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
        ) as mock_get,
    ):
        mock_post.return_value = _response(
            201, {"forecast_id": "f-1", "status": "PENDING"}
        )
        mock_get.side_effect = [
            _response(200, {"forecast_id": "f-1", "status": "RUNNING"}),
            _response(200, {"forecast_id": "f-1", "status": "SUCCEEDED"}),
        ]

        output = dispatch_run_forecast(
            {"region": NAMED_CALIFORNIA, "cutoff": "2024-08-15T10:00:00Z"}, backend
        )

    assert output == {"forecast_id": "f-1", "status": "SUCCEEDED"}
    mock_post.assert_called_once_with(
        "http://backend.test/forecasts",
        json={"region": NAMED_CALIFORNIA, "cutoff": "2024-08-15T10:00:00Z"},
        timeout=30,
    )


def test_dispatch_run_forecast_raises_on_a_failed_job():
    backend = Backend(base_url="http://backend.test", poll_interval_seconds=0)
    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.post"
        ) as mock_post,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
        ) as mock_get,
    ):
        mock_post.return_value = _response(
            201, {"forecast_id": "f-1", "status": "PENDING"}
        )
        mock_get.side_effect = [
            _response(200, {"forecast_id": "f-1", "status": "FAILED"}),
            _response(
                422, {"error": "no real FIRMS fire history for the requested cutoff"}
            ),
        ]

        with pytest.raises(StepFailed, match="no real FIRMS fire history"):
            dispatch_run_forecast(
                {"region": NAMED_CALIFORNIA, "cutoff": "2024-08-15T10:00:00Z"}, backend
            )


def test_dispatch_run_forecast_raises_on_a_timeout():
    backend = Backend(
        base_url="http://backend.test", poll_interval_seconds=0, max_wait_seconds=0
    )
    with patch(
        "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.post"
    ) as mock_post:
        mock_post.return_value = _response(
            201, {"forecast_id": "f-1", "status": "PENDING"}
        )

        with pytest.raises(StepFailed, match="did not finish within"):
            dispatch_run_forecast(
                {"region": NAMED_CALIFORNIA, "cutoff": "2024-08-15T10:00:00Z"}, backend
            )


def test_dispatch_get_result_evidence_returns_the_forecasts_own_evidence():
    backend = Backend(base_url="http://backend.test")
    evidence = {"dataset": "wildfire_forecast:v1", "processing_version": "0.1.0"}
    with patch(
        "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
    ) as mock_get:
        mock_get.return_value = _response(
            200, {"forecast_id": "f-1", "result": {"evidence": evidence}}
        )

        output = dispatch_get_result_evidence({"result_id": "f-1"}, backend)

    assert output == evidence
    mock_get.assert_called_once_with(
        "http://backend.test/forecasts/f-1/result", timeout=10
    )


def test_dispatch_get_forecast_result_summarizes_the_stored_result():
    backend = Backend(base_url="http://backend.test")
    evidence = {"dataset": "wildfire_forecast:v1"}
    feature = {
        "type": "Feature",
        "properties": {
            "tile_id": "t1",
            "centroid_lat": 37.05,
            "centroid_lon": -120.05,
            "probability": 0.0312,
        },
    }
    result = {
        "grid": {"type": "FeatureCollection", "features": [feature]},
        "model_version": "v1",
        "data_cutoff": "2024-08-15T10:00:00+00:00",
        "forecast_window": {"start": "a", "end": "b", "hours": 24},
        "evidence": evidence,
    }
    with patch(
        "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
    ) as mock_get:
        mock_get.return_value = _response(200, {"forecast_id": "f-1", "result": result})

        summary, summary_evidence = dispatch_get_forecast_result(
            {"result_id": "f-1"}, backend
        )

    assert summary["max_probability"] == 0.0312
    assert summary["top_cells"][0]["tile_id"] == "t1"
    assert summary_evidence == evidence


def test_dispatch_get_result_evidence_raises_when_the_forecast_has_not_finished():
    backend = Backend(base_url="http://backend.test")
    with patch(
        "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
    ) as mock_get:
        mock_get.return_value = _response(
            409, {"error": "forecast f-1 has not finished"}
        )

        with pytest.raises(requests.HTTPError):
            dispatch_get_result_evidence({"result_id": "f-1"}, backend)


def _step(step_id, tool, input, depends_on=()):
    return PlanStep(
        step_id=step_id, tool=tool, input=input, depends_on=tuple(depends_on)
    )


def test_execute_plan_runs_steps_in_order_and_resolves_refs(firms_history):
    plan = Plan(
        question="how many fires in California, and what does the forecast say?",
        steps=(
            _step(
                "count",
                "calculate_statistics",
                {
                    "region": NAMED_CALIFORNIA,
                    "time_range": AUGUST_2024,
                    "operation": "count",
                },
            ),
            _step(
                "forecast",
                "run_forecast",
                {
                    "region": NAMED_CALIFORNIA,
                    "cutoff": "2024-08-15T10:00:00Z",
                },
                depends_on=(),
            ),
            _step(
                "evidence",
                "get_result_evidence",
                {"result_id": "$forecast.forecast_id"},
                depends_on=("forecast",),
            ),
        ),
    )
    backend = Backend(base_url="http://backend.test", poll_interval_seconds=0)

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.post"
        ) as mock_post,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
        ) as mock_get,
    ):
        mock_post.return_value = _response(
            201, {"forecast_id": "f-42", "status": "PENDING"}
        )
        mock_get.side_effect = [
            _response(200, {"forecast_id": "f-42", "status": "SUCCEEDED"}),
            _response(
                200,
                {
                    "forecast_id": "f-42",
                    "result": {"evidence": {"dataset": "wildfire_forecast:v1"}},
                },
            ),
        ]

        execution = execute_plan(plan, backend)

    assert execution.outputs["count"]["count"] == 3
    assert execution.outputs["forecast"]["forecast_id"] == "f-42"
    assert (
        mock_get.call_args_list[1].args[0]
        == "http://backend.test/forecasts/f-42/result"
    )
    assert execution.outputs["evidence"]["dataset"] == "wildfire_forecast:v1"
    assert execution.evidence["count"]["dataset"] == "NASA_FIRMS:VIIRS_SNPP_SP"
    assert "forecast" not in execution.evidence
    assert "evidence" not in execution.evidence


def test_execute_plan_cancels_steps_depending_on_a_failed_step_without_running_them(
    firms_history,
):
    plan = Plan(
        question="forecast then use its evidence",
        steps=(
            _step(
                "forecast",
                "run_forecast",
                {"region": NAMED_CALIFORNIA, "cutoff": "2024-08-15T10:00:00Z"},
            ),
            _step(
                "evidence",
                "get_result_evidence",
                {"result_id": "$forecast.forecast_id"},
                depends_on=("forecast",),
            ),
            _step(
                "count",
                "calculate_statistics",
                {
                    "region": NAMED_CALIFORNIA,
                    "time_range": AUGUST_2024,
                    "operation": "count",
                },
            ),
        ),
    )
    backend = Backend(base_url="http://backend.test")

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.post"
        ) as mock_post,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
        ) as mock_get,
    ):
        mock_post.return_value = _response(
            400, {"error": "cutoff: must be an ISO 8601 date-time"}
        )

        with pytest.raises(StepFailed) as excinfo:
            execute_plan(plan, backend)

    assert "forecast" in str(excinfo.value)
    assert "evidence" in str(excinfo.value)
    assert "dependency 'forecast' failed" in str(excinfo.value)
    mock_get.assert_not_called()
    assert "count" not in str(excinfo.value)


def test_execute_plan_defends_against_a_ref_to_a_step_never_run_without_depends_on():
    plan = Plan(
        question="reference a step that never ran",
        steps=(
            _step(
                "forecast",
                "run_forecast",
                {"region": NAMED_CALIFORNIA, "cutoff": "2024-08-15T10:00:00Z"},
            ),
            _step(
                "evidence",
                "get_result_evidence",
                {"result_id": "$forecast.forecast_id"},
                depends_on=(),  # missing on purpose
            ),
        ),
    )
    backend = Backend(base_url="http://backend.test", poll_interval_seconds=0)

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.post"
        ) as mock_post,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.query.dispatch.requests.get"
        ) as mock_get,
    ):
        mock_post.return_value = _response(
            400, {"error": "cutoff: must be an ISO 8601 date-time"}
        )

        with pytest.raises(StepFailed, match="did not produce an output"):
            execute_plan(plan, backend)

    mock_get.assert_not_called()
