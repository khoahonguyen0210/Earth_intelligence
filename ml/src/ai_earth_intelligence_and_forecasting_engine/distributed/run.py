from __future__ import annotations

import os
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import parse_era5_records
from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    build_geography_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GridCell,
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    DistributedWorkload,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
    build_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CalibratedModel,
    fit_calibration,
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.profiling import (
    StageProfile,
    profile_stage,
    synthetic_timing_rows,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
)
from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    load_firms_observations,
)
from ai_earth_intelligence_and_forecasting_engine.query.run_forecast import (
    TRAIN_DEMO_CUTOFF,
    VALIDATION_DEMO_CUTOFF,
)

INFERENCE_CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)

FIT_CELL_COUNT = 100
MIN_SYNTHETIC_FIT_ROWS = 20


def fit_baseline_model(
    train_rows: list[DatasetRow], validation_rows: list[DatasetRow]
) -> tuple[CalibratedModel, bool]:
    """Returns whether the fallback was used."""
    try:
        base_result = fit_xgboost(train_rows, validation_rows)
        return fit_calibration(base_result, validation_rows), False
    except ValueError:
        synthetic_train = synthetic_timing_rows(
            max(len(train_rows), MIN_SYNTHETIC_FIT_ROWS), "train"
        )
        synthetic_validation = synthetic_timing_rows(
            max(len(validation_rows), MIN_SYNTHETIC_FIT_ROWS), "validation"
        )
        base_result = fit_xgboost(synthetic_train, synthetic_validation)
        return fit_calibration(base_result, synthetic_validation), True


def chunk_tile_ids(
    tile_ids: tuple[str, ...], num_workers: int
) -> list[tuple[str, ...]]:
    """Splits tile_ids into up to num_workers near-equal, contiguous,
    non-empty chunks. Returns fewer than num_workers chunks rather than
    any empty ones if there are fewer tiles than workers."""
    if num_workers < 1:
        raise ValueError(f"num_workers must be >= 1, got {num_workers}")

    total = len(tile_ids)
    base_size, remainder = divmod(total, num_workers)

    chunks: list[tuple[str, ...]] = []
    start = 0
    for worker_index in range(num_workers):
        size = base_size + (1 if worker_index < remainder else 0)
        if size == 0:
            continue
        chunks.append(tile_ids[start : start + size])
        start += size

    return chunks


@dataclass(frozen=True)
class WorkerChunkResult:
    tile_count: int
    cpu_seconds: float
    peak_memory_mb: float


@dataclass(frozen=True)
class ChunkTask:
    """One worker's unit of work; every field here must round-trip
    through pickle across the process boundary.

    inject_crash is the fault-injection switch: when True, the worker
    terminates itself immediately instead of doing any real work. Always
    False for a normal benchmark run."""

    tile_ids: tuple[str, ...]
    cutoff: datetime
    observations: list
    era5_records: list
    geography_cells: list
    cells_by_id: dict[str, GridCell]
    model: CalibratedModel
    inject_crash: bool = False


def process_chunk(task: ChunkTask) -> WorkerChunkResult:
    """Runs inside one worker process: builds real feature rows for this
    chunk's tiles and scores them with the model already fitted once in
    the parent. Must be a module-level name (not a closure) to be
    picklable at all under Windows' spawn start method.

    When task.inject_crash is set, this worker process terminates itself
    via os._exit before doing any real work."""
    if task.inject_crash:
        os._exit(1)

    target_cells = [task.cells_by_id[tile_id] for tile_id in task.tile_ids]

    tracemalloc.start()
    cpu_start = time.process_time()

    rows = build_dataset(
        task.observations,
        task.era5_records,
        task.geography_cells,
        target_cells,
        [task.cutoff],
    )
    predict_calibrated(task.model, rows)

    cpu_seconds = time.process_time() - cpu_start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return WorkerChunkResult(
        tile_count=len(rows),
        cpu_seconds=cpu_seconds,
        peak_memory_mb=peak / (1024 * 1024),
    )


@dataclass(frozen=True)
class RunContext:
    observations: list
    era5_records: list
    geography_cells: list
    cells_by_id: dict[str, GridCell]
    model: CalibratedModel
    used_synthetic_model_fallback: bool
    data_loading: StageProfile


def prepare_run_context(
    raw_firms_path: Path,
    raw_era5_path: Path,
    geography_bbox: tuple[float, float, float, float],
    dem_path: Path,
    landcover_path: Path,
) -> RunContext:
    def _load_inputs() -> tuple[list, list, list]:
        observations = load_firms_observations(raw_firms_path)
        era5_records = parse_era5_records(raw_era5_path)
        geography_cells = build_geography_grid(
            bbox=geography_bbox,
            resolution_deg=0.1,
            dem_path=dem_path,
            landcover_path=landcover_path,
        )
        return observations, era5_records, geography_cells

    (observations, era5_records, geography_cells), data_loading = profile_stage(
        "data_loading", _load_inputs
    )

    all_cells: list[GridCell] = build_california_grid()
    cells_by_id = {cell.tile_id: cell for cell in all_cells}

    # Fitting uses a fixed cell set (FIT_CELL_COUNT), independent of
    # whatever inference workload size a caller later requests.
    fit_cells = all_cells[:FIT_CELL_COUNT]
    train_rows = build_dataset(
        observations, era5_records, geography_cells, fit_cells, [TRAIN_DEMO_CUTOFF]
    )
    validation_rows = build_dataset(
        observations, era5_records, geography_cells, fit_cells, [VALIDATION_DEMO_CUTOFF]
    )
    model, used_synthetic_fallback = fit_baseline_model(train_rows, validation_rows)

    return RunContext(
        observations=observations,
        era5_records=era5_records,
        geography_cells=geography_cells,
        cells_by_id=cells_by_id,
        model=model,
        used_synthetic_model_fallback=used_synthetic_fallback,
        data_loading=data_loading,
    )


@dataclass(frozen=True)
class DistributedRunResult:
    requested_workers: int
    actual_workers: int
    workload_size: int
    wall_seconds: float
    throughput_tiles_per_second: float
    total_cpu_seconds: float
    peak_memory_mb: float
    used_synthetic_model_fallback: bool


def run_distributed_inference(
    workload: DistributedWorkload, num_workers: int, context: RunContext
) -> DistributedRunResult:
    chunks = chunk_tile_ids(workload.tile_ids, num_workers)
    tasks = [
        ChunkTask(
            tile_ids=chunk,
            cutoff=INFERENCE_CUTOFF,
            observations=context.observations,
            era5_records=context.era5_records,
            geography_cells=context.geography_cells,
            cells_by_id=context.cells_by_id,
            model=context.model,
        )
        for chunk in chunks
    ]

    wall_start = time.perf_counter()
    if len(tasks) == 1:
        chunk_results = [process_chunk(tasks[0])]
    else:
        with Pool(processes=len(tasks)) as pool:
            chunk_results = pool.map(process_chunk, tasks)
    wall_seconds = time.perf_counter() - wall_start

    total_tiles = sum(result.tile_count for result in chunk_results)
    total_cpu_seconds = sum(result.cpu_seconds for result in chunk_results)
    peak_memory_mb = max(result.peak_memory_mb for result in chunk_results)

    return DistributedRunResult(
        requested_workers=num_workers,
        actual_workers=len(chunks),
        workload_size=total_tiles,
        wall_seconds=wall_seconds,
        throughput_tiles_per_second=(
            total_tiles / wall_seconds if wall_seconds > 0 else float("inf")
        ),
        total_cpu_seconds=total_cpu_seconds,
        peak_memory_mb=peak_memory_mb,
        used_synthetic_model_fallback=context.used_synthetic_model_fallback,
    )
