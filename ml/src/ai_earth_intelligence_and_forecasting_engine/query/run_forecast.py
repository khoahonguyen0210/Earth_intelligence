from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GridCell,
    build_california_grid,
    cells_within_bbox,
)
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    LOOKBACK_HOURS,
    load_firms_history,
    require_firms_coverage,
)
from ai_earth_intelligence_and_forecasting_engine.data.live import (
    LIVE_FIRMS_PRODUCT,
    check_live_cutoff,
    ensure_live_era5,
    ensure_live_firms,
)
from ai_earth_intelligence_and_forecasting_engine.data.outlook import (
    check_outlook_cutoff,
    fetch_weather_outlook,
)
from ai_earth_intelligence_and_forecasting_engine.data.statewide_geography import (
    load_geography_records,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
    build_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.historical_dataset import (
    ERA5History,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.explain import (
    EXPLANATION_METHOD,
    EXPLANATION_UNITS,
    compute_contributions,
    mean_absolute_importance,
    top_drivers,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    ProductionModel,
    load_production_model,
    train_production_model,
)
from ai_earth_intelligence_and_forecasting_engine.query.forecast_result import (
    CellForecast,
    Explanation,
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
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec

TRAIN_DEMO_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
VALIDATION_DEMO_CUTOFF = datetime(2023, 8, 15, 10, 0, tzinfo=timezone.utc)

# The stalest ERA5-Land hour a forecast may use; older means there is no
# real weather to use.
MAX_ERA5_AGE = timedelta(days=7)


def parse_forecast_payload(payload: dict[str, Any]) -> ForecastRequest:
    region_payload = payload["region"]

    return ForecastRequest(
        region=RegionSpec(kind=region_payload["kind"], value=region_payload["value"]),
        cutoff=payload["cutoff"],
    )


def predict_forecast(
    model: ProductionModel,
    inference_rows: list[DatasetRow],
    target_cells: list[GridCell],
    region: NormalizedRegion,
    cutoff: datetime,
    timings_ms: dict[str, float] | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scores inference_rows with an already-trained model. `timings_ms`
    (if given) receives `model_inference`: scoring time only, not
    feature-building or model fitting."""
    inference_start = time.perf_counter()
    probabilities = predict_calibrated(model.calibrated, inference_rows)
    if timings_ms is not None:
        timings_ms["model_inference"] = (time.perf_counter() - inference_start) * 1000

    explain_start = time.perf_counter()
    contributions = compute_contributions(model.calibrated, inference_rows)
    if timings_ms is not None:
        timings_ms["explanation"] = (time.perf_counter() - explain_start) * 1000

    cell_by_tile_id = {cell.tile_id: cell for cell in target_cells}
    cells = [
        CellForecast(
            cell=cell_by_tile_id[row.tile_id],
            probability=probability,
            drivers=top_drivers(contributions.features, contributions.values[index]),
        )
        for index, (row, probability) in enumerate(
            zip(inference_rows, probabilities, strict=True)
        )
    ]
    explanation = Explanation(
        method=EXPLANATION_METHOD,
        units=EXPLANATION_UNITS,
        importance=mean_absolute_importance(contributions),
    )
    result = build_forecast_result(
        cells, region, cutoff, model.calibration_table, inputs, explanation
    )
    return forecast_result_to_dict(result)


def compute_forecast(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    inference_rows: list[DatasetRow],
    target_cells: list[GridCell],
    region: NormalizedRegion,
    cutoff: datetime,
    timings_ms: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Train-then-predict in one call: the locked calibrated-XGBoost
    pipeline fit from train_rows/validation_rows exactly as the
    production model is (models/production_model.py), then scored on
    inference_rows. `timings_ms` receives `model_fit` and
    `model_inference`."""
    fit_start = time.perf_counter()
    model = train_production_model(train_rows, validation_rows)
    if timings_ms is not None:
        timings_ms["model_fit"] = (time.perf_counter() - fit_start) * 1000

    return predict_forecast(
        model, inference_rows, target_cells, region, cutoff, timings_ms
    )


def require_lookback_coverage(history_dir: Path, cutoff: datetime) -> None:
    """A forecast needs real fire history for its whole 30-day lookback;
    outside it every fire-history feature would silently read 0."""
    require_firms_coverage(
        history_dir,
        cutoff - timedelta(hours=LOOKBACK_HOURS),
        cutoff,
        f"the 30 days before cutoff {cutoff.isoformat()}",
    )


def run_forecast(
    payload: dict[str, Any],
    firms_history_dir: Path,
    era5_history_dir: Path,
    geography_path: Path,
    model_dir: Path,
    live_dir: Path | None = None,
) -> dict[str, Any]:
    """Validates the request, builds the inference cutoff's feature rows
    from the real history (FIRMS strictly before the cutoff -- nothing
    after it is even loaded), and scores them with the trained
    production model.

    Returns {"result": ..., "timings_ms": {...}}. `timings_ms` sits
    beside the result, not inside it."""
    total_start = time.perf_counter()
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

    now = datetime.now(timezone.utc)
    outlook = live_dir is not None and cutoff > now
    live = False
    if outlook:
        check_outlook_cutoff(cutoff, now)
        data_cutoff = now
    else:
        data_cutoff = cutoff
        try:
            require_lookback_coverage(firms_history_dir, cutoff)
        except ValueError:
            if live_dir is None:
                raise
            check_live_cutoff(cutoff, now)
            live = True

    lookback_start = data_cutoff - timedelta(hours=LOOKBACK_HOURS)
    load_start = time.perf_counter()
    if outlook:
        assert live_dir is not None
        ensure_live_firms(live_dir, data_cutoff)
        observations = load_firms_history(
            live_dir, lookback_start, data_cutoff, LIVE_FIRMS_PRODUCT
        )
        era5_records = fetch_weather_outlook(
            target_cells, cutoff, data_cutoff - timedelta(hours=1)
        )
    elif live:
        assert live_dir is not None
        ensure_live_firms(live_dir, cutoff)
        observations = load_firms_history(
            live_dir, lookback_start, cutoff, LIVE_FIRMS_PRODUCT
        )
        era5_records = ensure_live_era5(live_dir, cutoff)
    else:
        observations = load_firms_history(firms_history_dir, lookback_start, cutoff)
        era5_records = ERA5History(era5_history_dir).for_cutoff(cutoff)
    fresh_era5 = [
        r for r in era5_records if data_cutoff - r.valid_time <= MAX_ERA5_AGE
    ]
    if not fresh_era5:
        raise ValueError(
            f"no real ERA5-Land weather within {MAX_ERA5_AGE.days} days before "
            f"{data_cutoff.isoformat()}"
        )
    geography = load_geography_records(geography_path)

    rows = build_dataset(
        observations, fresh_era5, geography, target_cells, [data_cutoff]
    )
    timings_ms: dict[str, float] = {
        "data_load": (time.perf_counter() - load_start) * 1000
    }

    model_start = time.perf_counter()
    model = load_production_model(model_dir)
    timings_ms["model_load"] = (time.perf_counter() - model_start) * 1000

    inputs: dict[str, Any] = {
        "mode": "outlook" if outlook else "live" if live else "history",
        "firms_observations": len(observations),
        "firms_window": {
            "start": lookback_start.isoformat(),
            "end": data_cutoff.isoformat(),
        },
        "era5_valid_time": max(r.valid_time for r in fresh_era5).isoformat(),
        "model": {
            key: model.metadata.get(key)
            for key in ("model", "model_version", "trained_at", "train", "validation")
        },
    }
    if outlook:
        inputs["weather_source"] = "Open-Meteo forecast"
        inputs["weather_valid_for"] = cutoff.isoformat()
        inputs["horizon_hours"] = round((cutoff - now).total_seconds() / 3600, 1)
    result = predict_forecast(
        model, rows, target_cells, region, cutoff, timings_ms, inputs
    )
    timings_ms["total"] = (time.perf_counter() - total_start) * 1000

    return {"result": result, "timings_ms": timings_ms}
