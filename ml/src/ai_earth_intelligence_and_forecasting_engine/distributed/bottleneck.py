from __future__ import annotations

import pickle
import time
from dataclasses import dataclass
from multiprocessing import Pool

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    INFERENCE_CUTOFF,
    ChunkTask,
    RunContext,
)

# Task 9.4's own fixed candidate list, verbatim from the handbook.
CANDIDATE_FACTORS: tuple[str, ...] = (
    "cpu",
    "i_o",
    "network",
    "database",
    "serialization",
    "coordination",
)


def _noop(value: int) -> int:
    """A trivial worker function: isolates pure process-spawn/coordination
    overhead (interpreter startup, Windows' `spawn` start method
    re-importing this module and everything transitively imported by it
    -- numpy, xgboost, scikit-learn, rasterio) from any of Task 9.2/9.3's
    real per-tile computation."""
    return value


@dataclass(frozen=True)
class SpawnOverhead:
    num_workers: int
    wall_seconds: float


def measure_spawn_overhead(num_workers: int) -> SpawnOverhead:
    """Real, direct measurement of what starting a Pool(num_workers) and
    having every worker return immediately costs, with zero real work
    mixed in -- this isolates "coordination" (the handbook's own
    candidate name for process-management/start overhead) from every
    other candidate factor."""
    if num_workers < 1:
        raise ValueError(f"num_workers must be >= 1, got {num_workers}")

    start = time.perf_counter()
    if num_workers == 1:
        _noop(0)
    else:
        with Pool(processes=num_workers) as pool:
            pool.map(_noop, range(num_workers))
    wall_seconds = time.perf_counter() - start

    return SpawnOverhead(num_workers=num_workers, wall_seconds=wall_seconds)


@dataclass(frozen=True)
class SerializationCost:
    pickle_seconds: float
    unpickle_seconds: float
    payload_bytes: int


def build_sample_chunk_task(context: RunContext, tile_id: str) -> ChunkTask:
    """A real, single-tile ChunkTask built from a real RunContext -- the
    same object shape multiprocessing.Pool.map actually sends across the
    process boundary for every real worker call."""
    return ChunkTask(
        tile_ids=(tile_id,),
        cutoff=INFERENCE_CUTOFF,
        observations=context.observations,
        era5_records=context.era5_records,
        geography_cells=context.geography_cells,
        cells_by_id=context.cells_by_id,
        model=context.model,
    )


def measure_serialization_cost(task: ChunkTask) -> SerializationCost:
    """Real, direct measurement of what pickling one worker's real
    ChunkTask actually costs -- the same pickle protocol
    multiprocessing.Pool.map uses internally to send an argument across
    the process boundary, applied directly rather than inferred from a
    Pool run's total wall time. Isolates "serialization" from
    "coordination": a task carries every worker's full copy of the real
    observations/era5_records/geography_cells and the fitted model
    (Task 9.2's RunContext), not just its own tile slice, so this cost
    scales with dataset size and worker count, not with tile count."""
    start = time.perf_counter()
    payload = pickle.dumps(task)
    pickle_seconds = time.perf_counter() - start

    start = time.perf_counter()
    pickle.loads(payload)
    unpickle_seconds = time.perf_counter() - start

    return SerializationCost(
        pickle_seconds=pickle_seconds,
        unpickle_seconds=unpickle_seconds,
        payload_bytes=len(payload),
    )


@dataclass(frozen=True)
class BottleneckReport:
    spawn_overhead: list[SpawnOverhead]
    serialization_cost: SerializationCost
    data_loading_seconds: float
    real_compute_seconds_for_full_workload: float
    dominant_factor: str
    reasoning: str


def identify_bottleneck(
    context: RunContext,
    worker_counts: tuple[int, ...],
    real_compute_seconds: float,
) -> BottleneckReport:
    """Task 9.4: compares four real, directly-measured numbers -- pure
    process-spawn overhead at each worker count, one real ChunkTask's
    serialization cost, the one-time data-loading stage (the handbook's
    own "i_o" candidate), and the actual per-tile compute time Task
    9.2/9.3 already measured -- and names whichever dominates. "network"
    and "database" are never reached: nothing in this pipeline makes a
    network or database call (it is pure in-process Python plus local
    multiprocessing), so they are correctly never the answer here, not
    candidates this function forgot to check."""
    spawn_overhead = [measure_spawn_overhead(n) for n in worker_counts]
    max_spawn_seconds = max(overhead.wall_seconds for overhead in spawn_overhead)

    sample_task = build_sample_chunk_task(context, next(iter(context.cells_by_id)))
    serialization_cost = measure_serialization_cost(sample_task)
    serialization_seconds = (
        serialization_cost.pickle_seconds + serialization_cost.unpickle_seconds
    )

    candidates = {
        "cpu": real_compute_seconds,
        "i_o": context.data_loading.wall_time_seconds,
        "serialization": serialization_seconds,
        "coordination": max_spawn_seconds,
    }
    dominant_factor = max(candidates, key=lambda name: candidates[name])

    reasoning = (
        f"coordination (process-spawn) cost {max_spawn_seconds:.3f}s at the "
        f"largest tested worker count vs. {real_compute_seconds:.3f}s of real "
        f"compute, {context.data_loading.wall_time_seconds:.3f}s of one-time "
        f"I/O, and {serialization_seconds:.3f}s of per-task (de)serialization. "
        "network/database are not reached at all by this pipeline."
    )

    return BottleneckReport(
        spawn_overhead=spawn_overhead,
        serialization_cost=serialization_cost,
        data_loading_seconds=context.data_loading.wall_time_seconds,
        real_compute_seconds_for_full_workload=real_compute_seconds,
        dominant_factor=dominant_factor,
        reasoning=reasoning,
    )
