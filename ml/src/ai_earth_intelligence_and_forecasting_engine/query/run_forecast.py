from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.era5 import parse_era5_records
from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    build_geography_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GridCell,
    build_california_grid,
    cells_within_bbox,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
    build_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    build_calibration_table,
    fit_calibration,
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
)
from ai_earth_intelligence_and_forecasting_engine.query.forecast_result import (
    CellForecast,
    ForecastRequest,
    build_forecast_result,
    forecast_result_to_dict,
    parse_cutoff,
    validate_forecast_request,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import (
    NormalizedRegion,
    normalize_region,
)
from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    load_firms_observations,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec

# The same real, known-good historical dates already used as demo train/
# validation cutoffs in scripts/models/run_final_benchmark.py -- a live
# forecast request only supplies the inference cutoff, so train/validation
# rows are always built at these two fixed points in the locked historical
# split (see docs/forecasting-specification.md).
TRAIN_DEMO_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
VALIDATION_DEMO_CUTOFF = datetime(2023, 8, 15, 10, 0, tzinfo=timezone.utc)


def parse_forecast_payload(payload: dict[str, Any]) -> ForecastRequest:
    region_payload = payload["region"]

    return ForecastRequest(
        region=RegionSpec(kind=region_payload["kind"], value=region_payload["value"]),
        cutoff=payload["cutoff"],
    )


def compute_forecast(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    inference_rows: list[DatasetRow],
    target_cells: list[GridCell],
    region: NormalizedRegion,
    cutoff: datetime,
) -> dict[str, Any]:
    """The pure model-fitting core: always the locked calibrated-XGBoost
    pipeline (Task 5.3 froze the full feature set; Task 6.1's contract
    makes calibration metadata a mandatory part of every result), fit
    fresh from train_rows/validation_rows and scored on inference_rows.
    """
    base_result = fit_xgboost(train_rows, validation_rows)
    calibrated = fit_calibration(base_result, validation_rows)

    validation_predictions = predict_calibrated(calibrated, validation_rows)
    calibration_table = build_calibration_table(
        [row.target for row in validation_rows], validation_predictions
    )

    inference_predictions = predict_calibrated(calibrated, inference_rows)
    cell_by_tile_id = {cell.tile_id: cell for cell in target_cells}
    cells = [
        CellForecast(cell=cell_by_tile_id[row.tile_id], probability=probability)
        for row, probability in zip(
            inference_rows, inference_predictions, strict=True
        )
    ]

    result = build_forecast_result(cells, region, cutoff, calibration_table)

    return forecast_result_to_dict(result)


def run_forecast(
    payload: dict[str, Any],
    raw_firms_path: Path,
    raw_era5_path: Path,
    geography_bbox: tuple[float, float, float, float],
    dem_path: Path,
    landcover_path: Path,
) -> dict[str, Any]:
    """The real-file orchestrator scripts/query/run_forecast_cli.py calls:
    parses/validates the request, loads the real Phase 1 sample data (the
    same files every scripts/models/run_*.py demo already reads), and
    delegates the actual fitting/prediction to compute_forecast."""
    request = parse_forecast_payload(payload)
    errors = validate_forecast_request(request)

    if errors:
        raise ValueError("; ".join(errors))

    region = normalize_region(request.region)
    cutoff = parse_cutoff(request.cutoff)

    target_cells = cells_within_bbox(build_california_grid(), region.bbox)

    if not target_cells:
        raise ValueError(
            f"No grid cells fall within the requested region: {region.bbox}"
        )

    observations = load_firms_observations(raw_firms_path)
    era5_records = parse_era5_records(raw_era5_path)
    geography_cells = build_geography_grid(
        bbox=geography_bbox,
        resolution_deg=0.1,
        dem_path=dem_path,
        landcover_path=landcover_path,
    )

    cutoffs = sorted({TRAIN_DEMO_CUTOFF, VALIDATION_DEMO_CUTOFF, cutoff})
    rows = build_dataset(
        observations, era5_records, geography_cells, target_cells, cutoffs
    )

    train_rows = [row for row in rows if row.cutoff == TRAIN_DEMO_CUTOFF]
    validation_rows = [row for row in rows if row.cutoff == VALIDATION_DEMO_CUTOFF]
    inference_rows = [row for row in rows if row.cutoff == cutoff]

    result = compute_forecast(
        train_rows, validation_rows, inference_rows, target_cells, region, cutoff
    )

    return {"result": result}
