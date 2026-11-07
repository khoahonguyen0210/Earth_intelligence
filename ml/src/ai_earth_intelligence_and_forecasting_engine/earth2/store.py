from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

FEATURES = ("hdw_max", "wind_max", "vpd_max", "t2m_max")


@dataclass(frozen=True)
class CutoffForecast:
    cutoff: datetime
    initialization: datetime
    latitude: np.ndarray
    longitude: np.ndarray
    features: dict[str, np.ndarray]
    approximate: bool


@dataclass(frozen=True)
class ForecastSet:
    cutoffs: list[datetime]
    latitude: np.ndarray
    longitude: np.ndarray
    features: dict[str, np.ndarray]
    metadata: dict[str, Any]

    def index_of(self, cutoff: datetime) -> int | None:
        try:
            return self.cutoffs.index(cutoff)
        except ValueError:
            return None


def cutoff_file_name(cutoff: datetime) -> str:
    return f"forecast_{cutoff.astimezone(timezone.utc):%Y%m%dT%H}.npz"


def save_cutoff_forecast(forecast: CutoffForecast, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / cutoff_file_name(forecast.cutoff)
    arrays: dict[str, Any] = {
        "cutoff": np.array(forecast.cutoff.isoformat()),
        "initialization": np.array(forecast.initialization.isoformat()),
        "latitude": forecast.latitude,
        "longitude": forecast.longitude,
        "approximate": np.array(forecast.approximate),
        **forecast.features,
    }
    np.savez_compressed(path, **arrays)
    return path


def load_cutoff_forecast(path: Path) -> CutoffForecast:
    with np.load(path) as stored:
        return CutoffForecast(
            cutoff=datetime.fromisoformat(str(stored["cutoff"])),
            initialization=datetime.fromisoformat(str(stored["initialization"])),
            latitude=stored["latitude"],
            longitude=stored["longitude"],
            features={name: stored[name] for name in FEATURES},
            approximate=bool(stored["approximate"]),
        )


def load_forecast_set(directory: Path) -> ForecastSet:
    forecasts = sorted(
        (load_cutoff_forecast(path) for path in directory.glob("forecast_*.npz")),
        key=lambda item: item.cutoff,
    )
    if not forecasts:
        raise FileNotFoundError(f"no forecast files in {directory}")
    first = forecasts[0]
    for forecast in forecasts:
        if forecast.initialization > forecast.cutoff:
            raise ValueError(f"{forecast.cutoff} starts after its cutoff")
        if not (
            np.array_equal(forecast.latitude, first.latitude)
            and np.array_equal(forecast.longitude, first.longitude)
        ):
            raise ValueError(f"{forecast.cutoff} uses a different grid")
    metadata_path = directory / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {}
    )
    return ForecastSet(
        cutoffs=[item.cutoff for item in forecasts],
        latitude=first.latitude,
        longitude=first.longitude,
        features={
            name: np.stack([item.features[name] for item in forecasts])
            for name in FEATURES
        },
        metadata=metadata,
    )
