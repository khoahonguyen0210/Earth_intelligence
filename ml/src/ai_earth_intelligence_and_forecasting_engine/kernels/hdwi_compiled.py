from __future__ import annotations

from functools import cache

import torch

from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
    compute_index,
    validate,
)

COMPILE_MODE = "max-autotune-no-cudagraphs"


@cache
def compiled_compute():
    return torch.compile(compute_index, mode=COMPILE_MODE, dynamic=False)


def compiled_hot_dry_windy_index(columns: ColumnFields) -> torch.Tensor:
    validate(columns)
    return compiled_compute()(columns)
