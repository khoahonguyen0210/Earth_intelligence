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

# Task 9.1 (Execution Handbook Phase 9): fixed per docs/distributed-
# workload.md, held fixed across every later Phase 9 task (9.2-9.5) --
# the whole point of that phase is to vary only the worker count between
# benchmark runs, never the workload/data/model. Reuses the project's
# already-locked version constants (Task 1.6's GRID_VERSION, Task 3.7's
# DATASET_VERSION/FEATURE_VERSION) rather than inventing new ones.
# ml/artifacts/calibrated_xgboost_v1/config.json
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
    """The first `workload_size` tiles from the real, versioned
    California grid (Task 1.6's build_california_grid), in the grid's
    own deterministic lat/lon-index order -- not randomly sampled, so
    every Phase 9 benchmark run (9.2-9.5) operates on the exact same
    tiles, and a fixed subset rather than the full ~10k-tile grid so a
    1-worker baseline (Task 9.2) finishes in a reasonable local runtime.
    """
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
