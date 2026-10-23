from __future__ import annotations

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    surface_vpd_from_relative_humidity,
)

INDEX_VERSION = "surface_hdw_v1"


def _column(rows: list[DatasetRow], name: str) -> np.ndarray:
    return np.array(
        [np.nan if getattr(row, name) is None else getattr(row, name) for row in rows],
        dtype=np.float64,
    )


def surface_index_components(rows: list[DatasetRow]) -> dict[str, np.ndarray]:
    temperature = _column(rows, "temperature_2m")
    humidity = _column(rows, "relative_humidity")
    wind = np.hypot(_column(rows, "u_wind_10m"), _column(rows, "v_wind_10m"))
    vpd = surface_vpd_from_relative_humidity(
        torch.from_numpy(temperature), torch.from_numpy(humidity)
    ).numpy()
    return {
        "surface_hdw": wind * vpd,
        "surface_vpd": vpd,
        "wind_speed_10m": wind,
    }


def complete_weather(components: dict[str, np.ndarray]) -> np.ndarray:
    return np.all(
        np.stack([np.isfinite(values) for values in components.values()]), axis=0
    )


def local_percentile(
    reference_tiles: list[str],
    reference_values: np.ndarray,
    tiles: list[str],
    values: np.ndarray,
) -> np.ndarray:
    history: dict[str, list[float]] = {}
    for tile, value in zip(reference_tiles, reference_values):
        if np.isfinite(value):
            history.setdefault(tile, []).append(float(value))
    sorted_history = {tile: np.sort(items) for tile, items in history.items()}

    result = np.full(len(values), np.nan)
    for index, (tile, value) in enumerate(zip(tiles, values)):
        past = sorted_history.get(tile)
        if past is None or not np.isfinite(value):
            continue
        result[index] = np.searchsorted(past, value, side="right") / len(past)
    return result
