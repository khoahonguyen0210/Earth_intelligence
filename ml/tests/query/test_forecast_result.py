import json
from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    build_california_grid,
    is_valid_polygon,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    FORECAST_WINDOW_HOURS,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CALIBRATION_METHOD,
    MODEL_VERSION,
    CalibrationBin,
)
from ai_earth_intelligence_and_forecasting_engine.query.forecast_result import (
    FORECAST_STATUS_VALUES,
    SYNCHRONOUS_STATUS_VALUES,
    CellForecast,
    ForecastRequest,
    build_forecast_grid,
    build_forecast_result,
    build_forecast_window,
    cell_forecast_to_feature,
    forecast_result_to_dict,
    parse_cutoff,
    validate_forecast_request,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec

GRID_CELLS = build_california_grid()
REGION = normalize_region(RegionSpec(kind="named", value="california"))
CUTOFF = datetime(2024, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_forecast_status_values_are_locked():
    assert FORECAST_STATUS_VALUES == (
        "PENDING",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "RETRYING",
        "CANCELLED",
    )


def test_synchronous_status_values_are_a_subset_of_the_full_lifecycle():
    assert set(SYNCHRONOUS_STATUS_VALUES) <= set(FORECAST_STATUS_VALUES)
    assert SYNCHRONOUS_STATUS_VALUES == ("SUCCEEDED", "FAILED")


def test_parse_cutoff_accepts_z_suffix():
    assert parse_cutoff("2024-08-03T12:00:00Z") == CUTOFF


def test_parse_cutoff_converts_offset_to_utc():
    assert parse_cutoff("2024-08-03T05:00:00-07:00") == CUTOFF


def test_parse_cutoff_assumes_utc_when_naive():
    assert parse_cutoff("2024-08-03T12:00:00") == CUTOFF


def test_parse_cutoff_rejects_unparseable_string():
    with pytest.raises(ValueError):
        parse_cutoff("not-a-datetime")


def test_validate_forecast_request_accepts_valid_request():
    request = ForecastRequest(
        region=RegionSpec(kind="named", value="california"),
        cutoff="2024-08-03T12:00:00Z",
    )

    assert validate_forecast_request(request) == []


def test_validate_forecast_request_rejects_unknown_region_kind():
    request = ForecastRequest(
        region=RegionSpec(kind="polygon", value="whatever"),
        cutoff="2024-08-03T12:00:00Z",
    )

    errors = validate_forecast_request(request)

    assert any("region.kind" in error for error in errors)


def test_validate_forecast_request_rejects_empty_cutoff():
    request = ForecastRequest(
        region=RegionSpec(kind="named", value="california"), cutoff="   "
    )

    errors = validate_forecast_request(request)

    assert any("cutoff must not be empty" in error for error in errors)


def test_validate_forecast_request_rejects_unparseable_cutoff():
    request = ForecastRequest(
        region=RegionSpec(kind="named", value="california"), cutoff="not-a-datetime"
    )

    errors = validate_forecast_request(request)

    assert any("ISO 8601" in error for error in errors)


def test_forecast_request_region_reuses_query_region_normalization():
    request = ForecastRequest(
        region=RegionSpec(kind="named", value="california"),
        cutoff="2024-08-03T12:00:00Z",
    )

    region = normalize_region(request.region)

    assert region.label == "california"
    assert region.bbox == CALIFORNIA_BBOX


def test_build_forecast_window_is_24_hours_after_cutoff():
    window = build_forecast_window(CUTOFF)

    assert window.start == CUTOFF
    assert window.end == datetime(2024, 8, 4, 12, 0, tzinfo=timezone.utc)
    assert window.hours == FORECAST_WINDOW_HOURS == 24


def test_cell_forecast_to_feature_carries_probability_and_geometry():
    cell = GRID_CELLS[0]
    feature = cell_forecast_to_feature(CellForecast(cell=cell, probability=0.42))

    assert feature["type"] == "Feature"
    assert feature["geometry"] == cell.geometry
    assert is_valid_polygon(feature["geometry"])
    assert feature["properties"]["tile_id"] == cell.tile_id
    assert feature["properties"]["probability"] == 0.42


def test_cell_forecast_to_feature_does_not_leak_probability_across_cells():
    cell = GRID_CELLS[0]
    first = cell_forecast_to_feature(CellForecast(cell=cell, probability=0.1))
    second = cell_forecast_to_feature(CellForecast(cell=cell, probability=0.9))

    assert first["properties"]["probability"] == 0.1
    assert second["properties"]["probability"] == 0.9


def test_build_forecast_grid_wraps_features_in_feature_collection():
    cells = [
        CellForecast(cell=GRID_CELLS[0], probability=0.1),
        CellForecast(cell=GRID_CELLS[1], probability=0.2),
    ]

    grid = build_forecast_grid(cells)

    assert grid["type"] == "FeatureCollection"
    assert len(grid["features"]) == 2
    assert grid["features"][0]["properties"]["probability"] == 0.1
    assert grid["features"][1]["properties"]["probability"] == 0.2


def test_build_forecast_grid_empty_list_is_valid_empty_collection():
    assert build_forecast_grid([]) == {"type": "FeatureCollection", "features": []}


def _sample_calibration_table() -> list[CalibrationBin]:
    return [
        CalibrationBin(
            bin_index=0, predicted_mean=0.05, observed_frequency=0.04, count=100
        )
    ]


def test_build_forecast_result_populates_locked_fields():
    result = build_forecast_result(
        cells=[CellForecast(cell=GRID_CELLS[0], probability=0.42)],
        region=REGION,
        cutoff=CUTOFF,
        calibration_table=_sample_calibration_table(),
    )

    assert result.model_version == MODEL_VERSION
    assert result.data_cutoff == CUTOFF
    assert result.forecast_window.start == CUTOFF
    assert result.forecast_window.hours == FORECAST_WINDOW_HOURS
    assert result.calibration.method == CALIBRATION_METHOD
    assert result.evidence.dataset == f"wildfire_forecast:{MODEL_VERSION}"
    assert result.evidence.region_label == "california"
    assert result.evidence.period_start == result.forecast_window.start.isoformat()
    assert result.evidence.period_end == result.forecast_window.end.isoformat()


def test_forecast_result_to_dict_is_json_serializable_and_shaped():
    result = build_forecast_result(
        cells=[CellForecast(cell=GRID_CELLS[0], probability=0.42)],
        region=REGION,
        cutoff=CUTOFF,
        calibration_table=_sample_calibration_table(),
    )

    payload = forecast_result_to_dict(result)
    json.dumps(payload)

    assert payload["model_version"] == MODEL_VERSION
    assert payload["data_cutoff"] == CUTOFF.isoformat()
    assert payload["forecast_window"] == {
        "start": result.forecast_window.start.isoformat(),
        "end": result.forecast_window.end.isoformat(),
        "hours": FORECAST_WINDOW_HOURS,
    }
    assert payload["grid"]["type"] == "FeatureCollection"
    assert payload["grid"]["features"][0]["properties"]["probability"] == 0.42
    assert payload["calibration"] == {
        "method": CALIBRATION_METHOD,
        "table": [
            {
                "bin_index": 0,
                "predicted_mean": 0.05,
                "observed_frequency": 0.04,
                "count": 100,
            }
        ],
    }
    assert payload["evidence"]["dataset"] == f"wildfire_forecast:{MODEL_VERSION}"
