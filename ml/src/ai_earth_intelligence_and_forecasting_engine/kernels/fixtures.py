from __future__ import annotations

import torch

from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
)

FCN3_LEVELS = (1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50)
DENSE_LEVELS = (1000, 975, 950, 925, 900, 875, 850, 825, 800, 775, 750, 700)

EDGE_CASES = (
    "typical",
    "calm_wind",
    "saturated_surface",
    "nan_surface",
    "nan_used_level",
    "nan_below_ground",
    "nan_above_layer",
    "nan_surface_pressure",
    "extreme_values",
    "high_terrain",
)


def random_columns(
    batch: tuple[int, ...],
    height: int,
    width: int,
    levels: tuple[int, ...] = FCN3_LEVELS,
    seed: int = 0,
    dtype: torch.dtype = torch.float32,
    device: torch.device | str = "cpu",
) -> ColumnFields:
    generator = torch.Generator(device=device).manual_seed(seed)
    grid = (*batch, height, width)
    stacked = (*batch, len(levels), height, width)

    def uniform(shape: tuple[int, ...], low: float, high: float) -> torch.Tensor:
        return low + (high - low) * torch.rand(
            shape, generator=generator, dtype=dtype, device=device
        )

    def normal(shape: tuple[int, ...], scale: float) -> torch.Tensor:
        return scale * torch.randn(
            shape, generator=generator, dtype=dtype, device=device
        )

    pressure = torch.tensor(levels, dtype=dtype, device=device)
    t2m = uniform(grid, 270.0, 315.0)
    lapse = (1000.0 - pressure).view(-1, 1, 1) * 0.07
    temperature = t2m.unsqueeze(-3) - lapse + normal(stacked, 2.0)

    return ColumnFields(
        t2m=t2m,
        d2m=t2m - uniform(grid, 0.0, 35.0),
        u10=normal(grid, 6.0),
        v10=normal(grid, 6.0),
        surface_pressure=uniform(grid, 60000.0, 103000.0),
        temperature=temperature,
        specific_humidity=uniform(stacked, 1e-4, 2e-2),
        u=normal(stacked, 9.0),
        v=normal(stacked, 9.0),
        pressure=pressure,
    )


def edge_case_columns(
    dtype: torch.dtype = torch.float64, device: torch.device | str = "cpu"
) -> ColumnFields:
    columns = random_columns(
        (), 1, len(EDGE_CASES), DENSE_LEVELS, seed=7, dtype=torch.float64
    )
    values = {
        name: getattr(columns, name).to(torch.float64).clone()
        for name in (
            "t2m",
            "d2m",
            "u10",
            "v10",
            "surface_pressure",
            "temperature",
            "specific_humidity",
            "u",
            "v",
        )
    }
    nan = float("nan")
    values["surface_pressure"][..., :] = 100000.0

    case = EDGE_CASES.index("calm_wind")
    for name in ("u10", "v10"):
        values[name][..., case] = 0.0
    for name in ("u", "v"):
        values[name][:, :, case] = 0.0

    case = EDGE_CASES.index("saturated_surface")
    values["d2m"][..., case] = values["t2m"][..., case]

    values["t2m"][..., EDGE_CASES.index("nan_surface")] = nan
    values["u"][1, 0, EDGE_CASES.index("nan_used_level")] = nan

    case = EDGE_CASES.index("nan_below_ground")
    values["surface_pressure"][..., case] = 95500.0
    values["temperature"][0, 0, case] = nan

    values["u"][-1, 0, EDGE_CASES.index("nan_above_layer")] = nan
    values["surface_pressure"][..., EDGE_CASES.index("nan_surface_pressure")] = nan

    case = EDGE_CASES.index("extreme_values")
    values["t2m"][..., case] = 330.0
    values["d2m"][..., case] = 230.0
    values["u10"][..., case] = 60.0
    values["temperature"][:, :, case] = 325.0
    values["specific_humidity"][:, :, case] = 1e-6
    values["u"][:, :, case] = 80.0

    values["surface_pressure"][..., EDGE_CASES.index("high_terrain")] = 70500.0

    return ColumnFields(**values, pressure=columns.pressure.to(torch.float64)).to(
        device, dtype
    )
