from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CALIBRATION_METHOD,
    MODEL_VERSION,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.run_forecast import (
    TRAIN_DEMO_CUTOFF,
    VALIDATION_DEMO_CUTOFF,
    compute_forecast,
    parse_forecast_payload,
    require_lookback_coverage,
    run_forecast,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec

TEST_BBOX = (-120.0, 37.0, -119.0, 38.0)
SELECTED_CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)[:20]
REGION = normalize_region(RegionSpec(kind="bbox", value=TEST_BBOX))
INFERENCE_CUTOFF = datetime(2024, 8, 3, 12, 0, tzinfo=timezone.utc)

REAL_FIRMS_HISTORY_DIR = Path("data/raw/firms/history")
REAL_ERA5_HISTORY_DIR = Path("data/raw/era5/history")
REAL_GEOGRAPHY_PATH = Path("data/raw/geography/california_geography.csv")
REAL_MODEL_DIR = Path("ml/artifacts/production_model_v1")
REAL_INPUTS_PRESENT = (
    REAL_FIRMS_HISTORY_DIR.is_dir()
    and REAL_ERA5_HISTORY_DIR.is_dir()
    and REAL_GEOGRAPHY_PATH.is_file()
    and (REAL_MODEL_DIR / "metadata.json").is_file()
)


def _row(
    tile_id: str, target: int, previous_24h_count: int, cutoff: datetime
) -> DatasetRow:
    return DatasetRow(
        tile_id=tile_id,
        cutoff=cutoff,
        split="unassigned",
        target=target,
        previous_24h_count=previous_24h_count,
        previous_72h_count=0,
        previous_7d_count=0,
        previous_30d_count=0,
        neighboring_previous_24h_count=0,
        temperature_2m=None,
        total_precipitation=None,
        u_wind_10m=None,
        v_wind_10m=None,
        relative_humidity=None,
        elevation_m=None,
        slope_deg=None,
        land_cover_class=None,
    )


def _separable_rows(cutoff: datetime) -> list[DatasetRow]:
    targets = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]
    counts = [50] * 10 + [0] * 10

    return [
        _row(cell.tile_id, target, count, cutoff)
        for cell, target, count in zip(SELECTED_CELLS, targets, counts, strict=True)
    ]


TRAIN_ROWS = _separable_rows(TRAIN_DEMO_CUTOFF)
VALIDATION_ROWS = _separable_rows(VALIDATION_DEMO_CUTOFF)
INFERENCE_ROWS = [
    _row(cell.tile_id, 0, 25, INFERENCE_CUTOFF) for cell in SELECTED_CELLS
]


def _run_real(payload: dict) -> dict:
    return run_forecast(
        payload,
        REAL_FIRMS_HISTORY_DIR,
        REAL_ERA5_HISTORY_DIR,
        REAL_GEOGRAPHY_PATH,
        REAL_MODEL_DIR,
    )


def test_parse_forecast_payload_builds_request():
    payload = {
        "region": {"kind": "named", "value": "california"},
        "cutoff": "2024-08-03T12:00:00Z",
    }

    request = parse_forecast_payload(payload)

    assert request.region.kind == "named"
    assert request.region.value == "california"
    assert request.cutoff == "2024-08-03T12:00:00Z"


def test_compute_forecast_returns_full_locked_shape():
    result = compute_forecast(
        TRAIN_ROWS,
        VALIDATION_ROWS,
        INFERENCE_ROWS,
        SELECTED_CELLS,
        REGION,
        INFERENCE_CUTOFF,
    )

    assert result["model_version"] == MODEL_VERSION
    assert result["data_cutoff"] == INFERENCE_CUTOFF.isoformat()
    assert result["forecast_window"] == {
        "start": INFERENCE_CUTOFF.isoformat(),
        "end": datetime(2024, 8, 4, 12, 0, tzinfo=timezone.utc).isoformat(),
        "hours": 24,
    }
    assert result["calibration"]["method"] == CALIBRATION_METHOD
    assert len(result["calibration"]["table"]) > 0
    assert result["evidence"]["dataset"] == f"wildfire_forecast:{MODEL_VERSION}"

    assert result["grid"]["type"] == "FeatureCollection"
    assert len(result["grid"]["features"]) == len(SELECTED_CELLS)

    for feature in result["grid"]["features"]:
        assert 0.0 <= feature["properties"]["probability"] <= 1.0


def test_compute_forecast_grid_features_are_keyed_to_correct_tile_ids():
    result = compute_forecast(
        TRAIN_ROWS,
        VALIDATION_ROWS,
        INFERENCE_ROWS,
        SELECTED_CELLS,
        REGION,
        INFERENCE_CUTOFF,
    )

    tile_ids_in_grid = {
        feature["properties"]["tile_id"] for feature in result["grid"]["features"]
    }

    assert tile_ids_in_grid == {cell.tile_id for cell in SELECTED_CELLS}


def test_compute_forecast_reports_model_stage_timings_when_asked():
    timings_ms: dict[str, float] = {}

    compute_forecast(
        TRAIN_ROWS,
        VALIDATION_ROWS,
        INFERENCE_ROWS,
        SELECTED_CELLS,
        REGION,
        INFERENCE_CUTOFF,
        timings_ms,
    )

    assert set(timings_ms) == {"model_fit", "model_inference"}
    assert all(value >= 0 for value in timings_ms.values())
    assert timings_ms["model_inference"] < timings_ms["model_fit"]


def test_compute_forecast_result_is_unchanged_by_timing():
    args = (
        TRAIN_ROWS,
        VALIDATION_ROWS,
        INFERENCE_ROWS,
        SELECTED_CELLS,
        REGION,
        INFERENCE_CUTOFF,
    )

    assert compute_forecast(*args) == compute_forecast(*args, {})


def test_compute_forecast_raises_on_single_class_training_data():
    single_class_train = [_row(SELECTED_CELLS[0].tile_id, 0, 0, TRAIN_DEMO_CUTOFF)]

    with pytest.raises(ValueError, match="only one class"):
        compute_forecast(
            single_class_train,
            VALIDATION_ROWS,
            INFERENCE_ROWS,
            SELECTED_CELLS,
            REGION,
            INFERENCE_CUTOFF,
        )


def test_run_forecast_rejects_invalid_region_kind():
    payload = {
        "region": {"kind": "polygon", "value": "x"},
        "cutoff": "2024-08-03T12:00:00Z",
    }

    with pytest.raises(ValueError, match="region.kind"):
        _run_real(payload)


def test_run_forecast_rejects_unparseable_cutoff():
    payload = {
        "region": {"kind": "named", "value": "california"},
        "cutoff": "not-a-datetime",
    }

    with pytest.raises(ValueError, match="ISO 8601"):
        _run_real(payload)


def test_require_lookback_coverage_refuses_a_cutoff_without_30_days_of_history(tmp_path):
    (tmp_path / "VIIRS_SNPP_SP_2024-08-01_5d.csv").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="no real FIRMS fire history"):
        require_lookback_coverage(tmp_path, datetime(2024, 8, 5, 10, tzinfo=timezone.utc))


def test_require_lookback_coverage_accepts_a_fully_covered_lookback(tmp_path):
    start = datetime(2024, 7, 1, tzinfo=timezone.utc).date()
    for offset in range(0, 40, 5):
        day = start + timedelta(days=offset)
        (tmp_path / f"VIIRS_SNPP_SP_{day.isoformat()}_5d.csv").write_text("x", encoding="utf-8")

    require_lookback_coverage(tmp_path, datetime(2024, 8, 5, 10, tzinfo=timezone.utc))


@pytest.mark.skipif(not REAL_INPUTS_PRESENT, reason="real history/model not built")
def test_run_forecast_end_to_end_on_real_history_and_the_trained_model():
    response = _run_real(
        {"region": {"kind": "named", "value": "california"}, "cutoff": "2024-08-10T10:00:00Z"}
    )

    result = response["result"]
    inputs = result["evidence"]["query_parameters"]["inputs"]
    assert result["grid"]["features"], "a real forecast covers real cells"
    assert all(0.0 <= f["properties"]["probability"] <= 1.0 for f in result["grid"]["features"])
    assert inputs["firms_observations"] > 0
    assert inputs["firms_window"]["end"] == "2024-08-10T10:00:00+00:00"
    assert inputs["era5_valid_time"] == "2024-08-10T10:00:00+00:00"
    assert inputs["model"]["train"]["positives"] > 0
    assert set(response["timings_ms"]) == {"data_load", "model_load", "model_inference", "total"}


@pytest.mark.skipif(not REAL_INPUTS_PRESENT, reason="real history/model not built")
def test_run_forecast_refuses_a_cutoff_outside_the_real_history():
    with pytest.raises(ValueError, match="no real FIRMS fire history"):
        _run_real({"region": {"kind": "named", "value": "california"},
                   "cutoff": "2025-08-15T10:00:00Z"})
