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

CANDIDATE_FACTORS: tuple[str, ...] = (
    "cpu",
    "i_o",
    "network",
    "database",
    "serialization",
    "coordination",
)


def _noop(value: int) -> int:
    return value


@dataclass(frozen=True)
class SpawnOverhead:
    num_workers: int
    wall_seconds: float


def measure_spawn_overhead(num_workers: int) -> SpawnOverhead:
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
