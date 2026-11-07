from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GridCell,
    locate_tile,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.earth2.store import ForecastSet
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    initialization_time,
    lead_window,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.labels import (
    is_qualifying_observation,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CalibratedModel,
    fit_calibration,
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.climatology import (
    fit_climatology,
    predict_climatology,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    persistence_scores,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
)

E7_VERSION = "e7_v1"
SPLIT_YEARS = {
    "train": (2019, 2020, 2021, 2022),
    "validation": (2023,),
    "test": (2025,),
}
BASE_FEATURES = (
    "previous_24h_count",
    "previous_72h_count",
    "previous_7d_count",
    "previous_30d_count",
    "neighboring_previous_24h_count",
    "elevation_m",
    "slope_deg",
)
FORECAST_FEATURES = (
    "forecast_hdw_max",
    "forecast_wind_max",
    "forecast_vpd_max",
    "forecast_t2m_max",
)
E7_FEATURES = BASE_FEATURES + FORECAST_FEATURES
NO_FORECAST_MODEL = "fire_history_geography"
FORECAST_MODEL = "with_forecast_weather"


@dataclass(frozen=True)
class E7Row(DatasetRow):
    lead_day: int
    forecast_hdw_max: float | None
    forecast_wind_max: float | None
    forecast_vpd_max: float | None
    forecast_t2m_max: float | None


def e7_split(cutoff: datetime) -> str | None:
    for split, years in SPLIT_YEARS.items():
        if cutoff.year in years:
            return split
    return None


def lead_fire_tiles(
    observations: list[Observation], cutoff: datetime, lead_day: int
) -> set[str]:
    start, end = lead_window(cutoff, lead_day)
    tiles = set()
    for observation in observations:
        if not is_qualifying_observation(observation):
            continue
        if not start < observation.observed_at <= end:
            continue
        tile = locate_tile(observation.latitude, observation.longitude)
        if tile is not None:
            tiles.add(tile)
    return tiles


def interpolate_to_cells(
    field: np.ndarray,
    latitude: np.ndarray,
    longitude: np.ndarray,
    cells: list[GridCell],
) -> np.ndarray:
    order = np.argsort(latitude)
    interpolator = RegularGridInterpolator(
        (latitude[order], longitude),
        field[order],
        method="linear",
        bounds_error=False,
        fill_value=np.nan,
    )
    points = np.array(
        [[cell.centroid_lat, cell.centroid_lon % 360.0] for cell in cells]
    )
    return interpolator(points)


def cell_forecasts(
    forecasts: ForecastSet, cells: list[GridCell], lead_day: int
) -> dict[datetime, dict[str, np.ndarray]]:
    lead = LEAD_DAYS.index(lead_day)
    return {
        cutoff: {
            f"forecast_{name}": interpolate_to_cells(
                values[index, lead], forecasts.latitude, forecasts.longitude, cells
            )
            for name, values in forecasts.features.items()
        }
        for index, cutoff in enumerate(forecasts.cutoffs)
    }


def _optional(value: float) -> float | None:
    return None if np.isnan(value) else float(value)


def build_lead_rows(
    base_rows: list[DatasetRow],
    lead_day: int,
    fire_tiles: dict[datetime, set[str]],
    forecasts: dict[datetime, dict[str, np.ndarray]],
    cell_index: dict[str, int],
) -> list[E7Row]:
    rows = []
    for row in base_rows:
        split = e7_split(row.cutoff)
        if split is None or row.cutoff not in forecasts:
            continue
        if initialization_time(row.cutoff) > row.cutoff:
            raise ValueError(f"forecast for {row.cutoff} starts after the cutoff")
        values = forecasts[row.cutoff]
        index = cell_index[row.tile_id]
        fields = dict(row.__dict__)
        fields.update(
            split=split,
            target=int(row.tile_id in fire_tiles[row.cutoff]),
            lead_day=lead_day,
            **{name: _optional(values[name][index]) for name in FORECAST_FEATURES},
        )
        rows.append(E7Row(**fields))
    return rows


def _rows(rows: Sequence[DatasetRow]) -> list[DatasetRow]:
    return list(rows)


def fit_lead_model(
    train: Sequence[DatasetRow],
    validation: Sequence[DatasetRow],
    features: tuple[str, ...],
) -> CalibratedModel:
    base = fit_xgboost(_rows(train), _rows(validation), feature_columns=features)
    return fit_calibration(base, _rows(validation))


def lead_scores(
    train: Sequence[DatasetRow],
    validation: Sequence[DatasetRow],
    test: Sequence[DatasetRow],
    locked_model: CalibratedModel | None,
) -> tuple[dict[str, np.ndarray], dict[str, CalibratedModel]]:
    models = {
        NO_FORECAST_MODEL: fit_lead_model(train, validation, BASE_FEATURES),
        FORECAST_MODEL: fit_lead_model(train, validation, E7_FEATURES),
    }
    climatology = fit_climatology(_rows(train))
    scores = {
        "climatology": np.array(predict_climatology(climatology, _rows(test))),
        "persistence_24h": np.array(persistence_scores(_rows(test), "24h")),
    }
    if locked_model is not None:
        scores["locked_24h_model"] = np.array(
            predict_calibrated(locked_model, _rows(test))
        )
    for name, model in models.items():
        scores[name] = np.array(predict_calibrated(model, _rows(test)))
    return scores, models
