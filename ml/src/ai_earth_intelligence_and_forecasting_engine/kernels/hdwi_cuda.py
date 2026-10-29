from __future__ import annotations

from functools import cache
from pathlib import Path
from types import ModuleType

import torch
from torch.utils.cpp_extension import load

from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.layout import (
    PackedColumns,
    pack,
)

SOURCE_DIR = Path(__file__).parent


@cache
def extension() -> ModuleType:
    return load(
        name="hdwi_cuda",
        sources=[
            str(SOURCE_DIR / "hdwi_cuda.cpp"),
            str(SOURCE_DIR / "hdwi_cuda.cu"),
        ],
        extra_cuda_cflags=["-O3"],
        verbose=False,
    )


def cuda_hot_dry_windy_index(columns: ColumnFields) -> torch.Tensor:
    return launch(pack(columns))


def launch(packed: PackedColumns) -> torch.Tensor:
    out = extension().hdwi(*packed.surface, *packed.levels, packed.pressure)
    return out.view(packed.grid)
