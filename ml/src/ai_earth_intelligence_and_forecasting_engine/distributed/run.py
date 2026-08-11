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

# Task 9.2/9.3: an arbitrary but fixed inference cutoff -- any real,
# parseable cutoff measures computational cost equally well; what Task
# 9.1 actually requires held fixed is the tiles/dataset/model, not which
# specific cutoff is used for inference.
INFERENCE_CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)

# How many cells to build train/validation rows from when fitting the
# one model every benchmark run holds fixed -- independent of whichever
# (possibly much smaller, e.g. in a test) inference workload size is
# requested. Fixed at a size comfortably above CalibratedClassifierCV's
# default 5-fold cross-validation minimum, so fitting never fails purely
# from too few *rows* on top of the already-handled too-few-*classes*
# case (see fit_baseline_model).
FIT_CELL_COUNT = 100
MIN_SYNTHETIC_FIT_ROWS = 20


def fit_baseline_model(
    train_rows: list[DatasetRow], validation_rows: list[DatasetRow]
) -> tuple[CalibratedModel, bool]:
    """Fits the one calibrated-XGBoost model every Phase 9 benchmark run
    holds fixed. Falls back to realistically-shaped synthetic rows
    (models.profiling.synthetic_timing_rows) on the exact same documented
    gap Task 5.4 already hit: the real train/validation splits have zero
    real historical positive examples in this project's small sample
    data, so calibration -- which needs both classes present in
    validation -- cannot fit a real model. Returns whether the fallback
    was used, the same `used_synthetic_timing_data` distinction
    profiling.py already reports, so a benchmark result is never silently
    unclear about which case produced it."""
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
    non-empty chunks -- contiguous purely so which chunk a tile lands in
    is easy to reason about, not because contiguity affects the
    computation itself. Returns fewer than num_workers chunks rather than
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
    """One worker's unit of work. A dataclass, not loose positional
    arguments: multiprocessing.Pool.map/apply_async pass a single
    picklable argument per call, and every field here must round-trip
    through pickle across the process boundary regardless.

    inject_crash is Task 9.5's fault-injection switch: when True, the
    worker terminates itself immediately instead of doing any real work
    (see process_chunk). Always False for every real Task 9.2/9.3 run."""

    tile_ids: tuple[str, ...]
    cutoff: datetime
    observations: list
    era5_records: list
    geography_cells: list
    cells_by_id: dict[str, GridCell]
    model: CalibratedModel
    inject_crash: bool = False


def process_chunk(task: ChunkTask) -> WorkerChunkResult:
    """Runs inside one worker process -- Task 9.2/9.3's actual unit of
    distributed work: builds real feature rows for this chunk's tiles
    (fire-history/environmental/geography joins, all real code, real
    sample data) and scores them with the model already fitted once in
    the parent. Must be a module-level name (not a closure) to be
    picklable at all under Windows' spawn start method.

    Task 9.5: when task.inject_crash is set, this worker process
    terminates itself via os._exit before doing any real work, instead
    of returning normally or raising. os._exit (not sys.exit or raising)
    is deliberate: it ends the process immediately with no Python-level
    cleanup or exception propagation, the same way an external `kill -9`
    would -- confirmed against the real interpreter that the parent
    Pool's corresponding AsyncResult.get() then raises
    multiprocessing.TimeoutError, never a distinct "worker died"
    exception, which is exactly why Task 9.5's fault-tolerant dispatcher
    detects failure via a timeout rather than an exception type."""
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
    """The real data + the one fitted model every worker-count run in a
    single benchmark (Task 9.2's num_workers=1 alone, or Task 9.3's
    1/2/4/8 sweep) shares unchanged -- prepared once by
    prepare_run_context, not re-loaded/re-fit per run. This is what
    actually makes "keep workload/data/model fixed" (the handbook's own
    words for Task 9.3) literally true across a sweep: the exact same
    model object, not just the same fitting recipe re-run each time."""

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
    """Loads the real Phase 1 sample data once and fits the one
    calibrated-XGBoost model a whole benchmark run (or sweep of runs)
    holds fixed. See fit_baseline_model for why fitting may fall back to
    synthetic-shaped rows, and RunContext's own docstring for why this is
    a separate, reusable step rather than folded into
    run_distributed_inference.

    The sample geography file covers a small fixed bounding box, not all
    of California (`scripts/query/run_forecast_cli.py`'s own
    GEOGRAPHY_BBOX), so most tiles drawn from the full California grid
    will genuinely get no geography match -- DatasetRow's geography
    fields are nullable for exactly this reason, and every other real
    join and the real prediction call still execute in full regardless.
    This benchmark measures computational cost, not feature
    completeness.
    """
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
    """Task 9.2 (num_workers=1) and Task 9.3 (num_workers=2/4/8) share
    this one real implementation and one prepared RunContext rather than
    each reimplementing/re-preparing it -- the handbook's own "keep
    workload/data/model fixed" requirement for a real speedup/efficiency
    comparison only holds if the code path and the fitted model
    genuinely do not change between runs, only the worker count."""
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
