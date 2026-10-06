from __future__ import annotations

from dataclasses import dataclass

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GRID_VERSION,
    GridCell,
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DATASET_VERSION,
    FEATURE_VERSION,
)

MODEL_VERSION = "calibrated_xgboost_v1"
WORKLOAD_SIZE = 500


@dataclass(frozen=True)
class DistributedWorkload:
    grid_version: str
    dataset_version: str
    feature_version: str
    model_version: str
    tile_ids: tuple[str, ...]

    @property
    def workload_size(self) -> int:
        return len(self.tile_ids)


def freeze_workload(workload_size: int = WORKLOAD_SIZE) -> DistributedWorkload:
    cells: list[GridCell] = build_california_grid()

    if workload_size > len(cells):
        raise ValueError(
            f"workload_size {workload_size} exceeds the grid's {len(cells)} tiles"
        )

    tile_ids = tuple(cell.tile_id for cell in cells[:workload_size])

    return DistributedWorkload(
        grid_version=GRID_VERSION,
        dataset_version=DATASET_VERSION,
        feature_version=FEATURE_VERSION,
        model_version=MODEL_VERSION,
        tile_ids=tile_ids,
    )
