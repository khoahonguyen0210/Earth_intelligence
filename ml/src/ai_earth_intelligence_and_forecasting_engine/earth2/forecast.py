from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    FEATURES,
    CutoffForecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    daily_valid_times,
    forecast_steps,
    initialization_time,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    KELVIN,
    MAGNUS_A,
    MAGNUS_B,
    MAGNUS_C,
    ColumnFields,
    index_components,
    vapor_pressure,
)

INDEX_LEVELS_HPA = (1000, 925, 850, 700, 600, 500)
CROP_LATITUDE = (31.5, 43.0)
CROP_LONGITUDE = (234.5, 247.0)
INDEX_VERSION = "hdwi_v1"
APPROXIMATE_INDEX_VERSION = "hdwi_approx_v1"


def dewpoint_from_vapor_pressure(vapor_hpa: torch.Tensor) -> torch.Tensor:
    ratio = torch.log(vapor_hpa / MAGNUS_A)
    return MAGNUS_C * ratio / (MAGNUS_B - ratio) + KELVIN


def lowest_level_above_ground(
    values: torch.Tensor, pressure_hpa: torch.Tensor, surface_hpa: torch.Tensor
) -> torch.Tensor:
    above = pressure_hpa.view(-1, 1, 1) <= surface_hpa.unsqueeze(-3)
    first = torch.argmax(above.to(torch.int8), dim=-3, keepdim=True)
    return torch.gather(values, -3, first).squeeze(-3)


def required_variables(levels: tuple[int, ...] = INDEX_LEVELS_HPA) -> list[str]:
    surface = ["t2m", "u10m", "v10m", "sp"]
    return surface + [f"{name}{level}" for name in "tquv" for level in levels]


def build_columns(
    fields: dict[str, torch.Tensor], levels: tuple[int, ...] = INDEX_LEVELS_HPA
) -> tuple[ColumnFields, bool]:
    missing = [name for name in required_variables(levels) if name not in fields]
    if missing:
        raise ValueError(f"model output is missing {missing}")
    t2m = fields["t2m"]
    pressure = torch.tensor(levels, dtype=t2m.dtype, device=t2m.device)

    def stack(prefix: str) -> torch.Tensor:
        return torch.stack([fields[f"{prefix}{level}"] for level in levels], dim=-3)

    humidity = stack("q")
    surface_hpa = fields["sp"] / 100.0
    approximate = "d2m" not in fields
    if approximate:
        lowest = lowest_level_above_ground(humidity, pressure, surface_hpa)
        d2m = dewpoint_from_vapor_pressure(vapor_pressure(lowest, surface_hpa))
    else:
        d2m = fields["d2m"]
    columns = ColumnFields(
        t2m=t2m,
        d2m=d2m,
        u10=fields["u10m"],
        v10=fields["v10m"],
        surface_pressure=fields["sp"],
        temperature=stack("t"),
        specific_humidity=humidity,
        u=stack("u"),
        v=stack("v"),
        pressure=pressure,
    )
    return columns, approximate


def daily_features(snapshots: list[ColumnFields]) -> dict[str, torch.Tensor]:
    if not snapshots:
        raise ValueError("a lead day needs at least one forecast time")
    values: dict[str, list[torch.Tensor]] = {name: [] for name in FEATURES}
    for columns in snapshots:
        wind, vpd = index_components(columns)
        missing = torch.isnan(columns.surface_pressure)
        index = torch.where(missing, columns.surface_pressure, wind * vpd)
        values["hdw_max"].append(index)
        values["wind_max"].append(wind)
        values["vpd_max"].append(vpd)
        values["t2m_max"].append(columns.t2m)
    return {name: torch.stack(items).amax(dim=0) for name, items in values.items()}


def crop_indices(
    latitude: np.ndarray, longitude: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    rows = np.flatnonzero(
        (latitude >= CROP_LATITUDE[0]) & (latitude <= CROP_LATITUDE[1])
    )
    columns = np.flatnonzero(
        (longitude >= CROP_LONGITUDE[0]) & (longitude <= CROP_LONGITUDE[1])
    )
    if rows.size == 0 or columns.size == 0:
        raise ValueError("model grid does not cover California")
    return rows, columns


def select_fields(
    output: torch.Tensor,
    coords: dict[str, np.ndarray],
    names: list[str],
    rows: np.ndarray,
    columns: np.ndarray,
) -> dict[str, torch.Tensor]:
    dims = list(coords)
    index = tuple(
        slice(None) if dim in ("variable", "lat", "lon") else -1 for dim in dims
    )
    grid = output[index]
    grid = grid[:, torch.as_tensor(rows, device=grid.device)]
    grid = grid[:, :, torch.as_tensor(columns, device=grid.device)]
    variables = [str(name) for name in coords["variable"]]
    return {
        name: grid[variables.index(name)] for name in names if name in variables
    }


def forecast_cutoff(
    model: Any, data: Any, cutoff: datetime, device: str = "cuda"
) -> CutoffForecast:
    from earth2studio.data import fetch_data
    from earth2studio.utils.time import to_time_array

    initialization = initialization_time(cutoff)
    lead_by_time = {
        time: lead for lead in LEAD_DAYS for time in daily_valid_times(cutoff, lead)
    }
    steps = forecast_steps(cutoff)
    coords = model.input_coords()
    x, x_coords = fetch_data(
        data,
        to_time_array([initialization.replace(tzinfo=None)]),
        coords["variable"],
        coords["lead_time"],
        device=torch.device(device),
    )
    names = required_variables() + ["d2m"]
    snapshots: dict[int, list[ColumnFields]] = {lead: [] for lead in LEAD_DAYS}
    approximate = False
    latitude = longitude = np.empty(0)
    with torch.inference_mode():
        for step, (output, output_coords) in enumerate(
            model.create_iterator(x, x_coords)
        ):
            hours = int(output_coords["lead_time"][-1] / np.timedelta64(1, "h"))
            valid = initialization + timedelta(hours=hours)
            if valid in lead_by_time:
                rows, columns = crop_indices(output_coords["lat"], output_coords["lon"])
                latitude = output_coords["lat"][rows]
                longitude = output_coords["lon"][columns]
                fields = select_fields(output, output_coords, names, rows, columns)
                fields = {name: value.double() for name, value in fields.items()}
                column_fields, approximate = build_columns(fields)
                snapshots[lead_by_time[valid]].append(column_fields)
            if step >= steps:
                break

    by_lead = [daily_features(snapshots[lead]) for lead in LEAD_DAYS]
    return CutoffForecast(
        cutoff=cutoff,
        initialization=initialization,
        latitude=np.asarray(latitude, dtype=np.float64),
        longitude=np.asarray(longitude, dtype=np.float64),
        features={
            name: np.stack([day[name].cpu().numpy() for day in by_lead])
            for name in FEATURES
        },
        approximate=approximate,
    )
