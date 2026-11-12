from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.data.grid import GridCell
from ai_earth_intelligence_and_forecasting_engine.earth2.e7 import (
    E7Row,
    interpolate_to_cells,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.portable import predict
from ai_earth_intelligence_and_forecasting_engine.earth2.store import CutoffForecast
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    lead_window,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    fire_history_features as fhf,
)

HIDDEN_LAND_COVER = (0, 80)
MAX_RUNS = 30


@dataclass(frozen=True)
class CellGeography:
    elevation_m: float
    slope_deg: float
    land_cover_class: int


def save_cell_geography(geography: dict[str, CellGeography], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["tile_id", "elevation_m", "slope_deg", "land_cover_class"])
        for tile_id in sorted(geography):
            place = geography[tile_id]
            writer.writerow(
                [
                    tile_id,
                    round(place.elevation_m, 1),
                    round(place.slope_deg, 2),
                    place.land_cover_class,
                ]
            )
    return path


def load_cell_geography(path: Path) -> dict[str, CellGeography]:
    with path.open(encoding="utf-8") as handle:
        return {
            row["tile_id"]: CellGeography(
                elevation_m=float(row["elevation_m"]),
                slope_deg=float(row["slope_deg"]),
                land_cover_class=int(row["land_cover_class"]),
            )
            for row in csv.DictReader(handle)
        }


def map_rows(
    cells: list[GridCell],
    geography: dict[str, CellGeography],
    fire_history: dict[str, fhf.FireHistoryFeatures],
    forecast: CutoffForecast,
    lead_day: int,
) -> list[E7Row]:
    lead = LEAD_DAYS.index(lead_day)
    values = {
        f"forecast_{name}": interpolate_to_cells(
            field[lead], forecast.latitude, forecast.longitude, cells
        )
        for name, field in forecast.features.items()
    }
    rows = []
    for index, cell in enumerate(cells):
        place = geography.get(cell.tile_id)
        if place is None or place.land_cover_class in HIDDEN_LAND_COVER:
            continue
        history = fire_history[cell.tile_id]
        forecast_values = {
            name: None if np.isnan(column[index]) else float(column[index])
            for name, column in values.items()
        }
        rows.append(
            E7Row(
                tile_id=cell.tile_id,
                cutoff=forecast.cutoff,
                split="live",
                target=0,
                previous_24h_count=history.previous_24h_count,
                previous_72h_count=history.previous_72h_count,
                previous_7d_count=history.previous_7d_count,
                previous_30d_count=history.previous_30d_count,
                neighboring_previous_24h_count=history.neighboring_previous_24h_count,
                temperature_2m=None,
                total_precipitation=None,
                u_wind_10m=None,
                v_wind_10m=None,
                relative_humidity=None,
                elevation_m=place.elevation_m,
                slope_deg=place.slope_deg,
                land_cover_class=place.land_cover_class,
                lead_day=lead_day,
                **forecast_values,
            )
        )
    return rows


def risk_payload(
    forecast: CutoffForecast,
    models: dict[int, dict[str, Any]],
    rows_by_lead: dict[int, list[E7Row]],
    model_metadata: dict[str, Any],
) -> dict[str, Any]:
    tiles = [row.tile_id for row in rows_by_lead[LEAD_DAYS[0]]]
    leads = []
    for lead in LEAD_DAYS:
        rows = rows_by_lead[lead]
        if [row.tile_id for row in rows] != tiles:
            raise ValueError("every lead day must cover the same cells")
        start, end = lead_window(forecast.cutoff, lead)
        risk = predict(models[lead], rows)
        leads.append(
            {
                "lead_day": lead,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "risk": [round(float(value), 5) for value in risk],
            }
        )
    return {
        "cutoff": forecast.cutoff.isoformat(),
        "forecast_start": forecast.initialization.isoformat(),
        "model": model_metadata,
        "tiles": tiles,
        "leads": leads,
    }


def update_runs(previous: list[dict[str, Any]], run: dict[str, Any]) -> list[dict]:
    kept = [item for item in previous if item.get("cutoff") != run["cutoff"]]
    return (kept + [run])[-MAX_RUNS:]
