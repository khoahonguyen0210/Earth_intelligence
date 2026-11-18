from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.kernels.bench import (  # noqa: E402
    bytes_moved,
    repeated,
    sector_bytes,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.fixtures import (  # noqa: E402
    FCN3_LEVELS,
    columns_from_fields,
    era5_variables,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (  # noqa: E402
    ColumnFields,
)

LEVELS = (1000, 925, 850)


def columns_with_surface(surface_hpa: list[float]) -> ColumnFields:
    width = len(surface_hpa)
    grid = torch.ones(1, 1, width)
    stacked = torch.ones(1, len(LEVELS), 1, width)
    return ColumnFields(
        t2m=grid * 300.0,
        d2m=grid * 280.0,
        u10=grid,
        v10=grid,
        surface_pressure=torch.tensor(surface_hpa).view(1, 1, width) * 100.0,
        temperature=stacked * 290.0,
        specific_humidity=stacked * 0.005,
        u=stacked,
        v=stacked,
        pressure=torch.tensor(LEVELS, dtype=torch.float32),
    )


def test_sectors_equal_the_minimum_when_neighbors_share_levels():
    columns = columns_with_surface([1013.0] * 8 + [880.0] * 8)
    assert bytes_moved(columns) == 4 * (6 * 16 + 4 * (8 * 2 + 8 * 1))
    assert sector_bytes(columns) == bytes_moved(columns)


def test_mixed_neighbors_touch_more_sectors_than_they_need():
    columns = columns_with_surface([1013.0, 880.0] * 8)
    assert bytes_moved(columns) == 768
    assert sector_bytes(columns) == 4 * 6 * 16 + 4 * 32 * 6


def test_a_partial_sector_counts_as_a_whole_one():
    columns = columns_with_surface([1013.0] * 3)
    assert sector_bytes(columns) == 4 * 6 * 3 + 4 * 32 * 2


def test_repeated_columns_are_real_copies():
    columns = repeated(columns_with_surface([1013.0] * 4), 3)
    assert columns.t2m.shape == (3, 1, 1, 4)
    assert columns.t2m.is_contiguous()
    assert columns.pressure.shape == (len(LEVELS),)


def test_fields_become_columns_in_level_order():
    names = era5_variables()
    assert names[:5] == ["t2m", "d2m", "u10m", "v10m", "sp"]
    assert len(names) == 5 + 4 * len(FCN3_LEVELS)
    fields = {
        name: torch.full((2, 3), float(index)) for index, name in enumerate(names)
    }
    columns = columns_from_fields(fields)
    assert columns.temperature.shape == (len(FCN3_LEVELS), 2, 3)
    assert float(columns.temperature[0, 0, 0]) == names.index("t1000")
    assert float(columns.v[-1, 0, 0]) == names.index("v50")
    assert float(columns.surface_pressure[0, 0]) == names.index("sp")
    assert columns.pressure.tolist() == list(FCN3_LEVELS)
