from __future__ import annotations

from ai_earth_intelligence_and_forecasting_engine.query.forecast_summary import (
    TOP_CELLS,
    summarize_forecast_result,
)


def _feature(tile_id: str, probability: float) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "tile_id": tile_id,
            "centroid_lat": 37.05,
            "centroid_lon": -120.05,
            "probability": probability,
            "top_drivers": [{"feature": "previous_7d_count", "contribution": 1.2}],
        },
    }


def _result(probabilities: list[float], explanation: bool = True) -> dict:
    result = {
        "grid": {
            "type": "FeatureCollection",
            "features": [
                _feature(f"t{index}", probability)
                for index, probability in enumerate(probabilities)
            ],
        },
        "model_version": "v1",
        "data_cutoff": "2024-08-15T10:00:00+00:00",
        "forecast_window": {"start": "a", "end": "b", "hours": 24},
        "calibration": {"method": "isotonic", "table": []},
        "evidence": {"dataset": "wildfire_forecast:v1"},
    }
    if explanation:
        result["explanation"] = {
            "method": "xgboost_tree_shap",
            "units": "log_odds",
            "importance": [
                {"feature": f"f{index}", "contribution": 1.0 - index / 10}
                for index in range(8)
            ],
        }
    return result


def test_summary_ranks_the_riskiest_cells_and_aggregates_the_region():
    summary = summarize_forecast_result(
        "f-1", _result([0.01, 0.2, 0.05, 0.3, 0.0, 0.07, 0.11])
    )

    assert summary["forecast_id"] == "f-1"
    assert summary["cell_count"] == 7
    assert summary["max_probability"] == 0.3
    assert summary["mean_probability"] == round(0.74 / 7, 4)
    assert [cell["tile_id"] for cell in summary["top_cells"]] == [
        "t3",
        "t1",
        "t6",
        "t5",
        "t2",
    ]
    assert len(summary["top_cells"]) == TOP_CELLS
    assert summary["top_cells"][0]["top_drivers"][0]["feature"] == "previous_7d_count"
    assert [entry["feature"] for entry in summary["drivers"]] == [
        "f0",
        "f1",
        "f2",
        "f3",
        "f4",
    ]
    assert summary["explanation_units"] == "log_odds"


def test_summary_of_a_result_without_explanation_or_cells():
    summary = summarize_forecast_result("f-2", _result([], explanation=False))

    assert summary["cell_count"] == 0
    assert summary["max_probability"] is None
    assert summary["mean_probability"] is None
    assert summary["top_cells"] == []
    assert summary["drivers"] == []
    assert summary["explanation_units"] is None
