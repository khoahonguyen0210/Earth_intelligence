from datetime import datetime, timezone
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
    run_forecast,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec

TEST_BBOX = (-120.0, 37.0, -119.0, 38.0)
SELECTED_CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)[:20]
REGION = normalize_region(RegionSpec(kind="bbox", value=TEST_BBOX))
INFERENCE_CUTOFF = datetime(2024, 8, 3, 12, 0, tzinfo=timezone.utc)

# The same real sample data every scripts/models/run_*.py demo already
# reads -- see docs/feature-set-freeze.md for why real historical data
# currently has zero real positive examples in train/validation.
REAL_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
REAL_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
REAL_GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
REAL_DEM_PATH = Path("data/raw/geography/dem_sample.tif")
REAL_LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")


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
        REAL_FIRMS_PATH,
        REAL_ERA5_PATH,
        REAL_GEOGRAPHY_BBOX,
        REAL_DEM_PATH,
        REAL_LANDCOVER_PATH,
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
