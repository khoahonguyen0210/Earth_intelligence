from __future__ import annotations

from dataclasses import dataclass

import torch

from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
    validate,
)

SURFACE_FIELDS = ("t2m", "d2m", "u10", "v10", "surface_pressure")
LEVEL_FIELDS = ("temperature", "specific_humidity", "u", "v")


@dataclass(frozen=True)
class PackedColumns:
    surface: tuple[torch.Tensor, ...]
    levels: tuple[torch.Tensor, ...]
    pressure: torch.Tensor
    grid: tuple[int, ...]
    batch: int
    columns: int


def pack(columns: ColumnFields, check: bool = True) -> PackedColumns:
    if check:
        validate(columns)
    grid = tuple(columns.t2m.shape)
    count = columns.pressure.numel()
    width = grid[-2] * grid[-1]
    batch = 1
    for size in grid[:-2]:
        batch *= size

    def prepare(tensor: torch.Tensor, shape: tuple[int, ...]) -> torch.Tensor:
        return tensor.to(torch.float32).reshape(shape).contiguous()

    return PackedColumns(
        surface=tuple(
            prepare(getattr(columns, name), (batch, width)) for name in SURFACE_FIELDS
        ),
        levels=tuple(
            prepare(getattr(columns, name), (batch, count, width))
            for name in LEVEL_FIELDS
        ),
        pressure=prepare(columns.pressure, (count,)),
        grid=grid,
        batch=batch,
        columns=width,
    )
