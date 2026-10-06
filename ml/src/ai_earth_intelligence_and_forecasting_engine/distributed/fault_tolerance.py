from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from multiprocessing.pool import AsyncResult, Pool

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    INFERENCE_CUTOFF,
    ChunkTask,
    RunContext,
    WorkerChunkResult,
    chunk_tile_ids,
    process_chunk,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    DistributedWorkload,
)

POLL_INTERVAL_SECONDS = 0.05


@dataclass(frozen=True)
class ChunkOutcome:
    chunk_index: int
    result: WorkerChunkResult | None
    attempts: int
    failure_detected: bool
    recovery_seconds: float | None


@dataclass(frozen=True)
class FaultTolerantRunResult:
    chunk_outcomes: list[ChunkOutcome]
    total_tiles: int
    any_failure_detected: bool
    all_chunks_eventually_succeeded: bool
    total_recovery_seconds: float


def _build_task(
    chunk: tuple[str, ...], context: RunContext, inject_crash: bool
) -> ChunkTask:
    return ChunkTask(
        tile_ids=chunk,
        cutoff=INFERENCE_CUTOFF,
        observations=context.observations,
        era5_records=context.era5_records,
        geography_cells=context.geography_cells,
        cells_by_id=context.cells_by_id,
        model=context.model,
        inject_crash=inject_crash,
    )


@dataclass
class _PendingChunk:
    chunk_index: int
    task: ChunkTask
    async_result: AsyncResult
    dispatched_at: float
    attempts: int
    failure_detected: bool = False
    failure_detected_at: float | None = None


def run_with_fault_tolerance(
    workload: DistributedWorkload,
    num_workers: int,
    context: RunContext,
    task_timeout_seconds: float,
    max_retries: int,
    inject_crash_in_chunk: int | None = None,
) -> FaultTolerantRunResult:
    chunks = chunk_tile_ids(workload.tile_ids, num_workers)

    with Pool(processes=len(chunks)) as pool:
        pending: dict[int, _PendingChunk] = {}
        for chunk_index, chunk in enumerate(chunks):
            task = _build_task(
                chunk, context, inject_crash=(chunk_index == inject_crash_in_chunk)
            )
            pending[chunk_index] = _PendingChunk(
                chunk_index=chunk_index,
                task=task,
                async_result=pool.apply_async(process_chunk, (task,)),
                dispatched_at=time.perf_counter(),
                attempts=1,
            )

        outcomes: dict[int, ChunkOutcome] = {}

        while pending:
            for chunk_index in list(pending.keys()):
                pending_chunk = pending[chunk_index]

                if pending_chunk.async_result.ready():
                    _resolve_ready_chunk(
                        pool, pending, outcomes, chunk_index, max_retries
                    )
                elif (
                    time.perf_counter() - pending_chunk.dispatched_at
                    > task_timeout_seconds
                ):
                    _handle_timeout(pool, pending, outcomes, chunk_index, max_retries)

            if pending:
                time.sleep(POLL_INTERVAL_SECONDS)

    ordered_outcomes = [outcomes[i] for i in range(len(chunks))]

    return FaultTolerantRunResult(
        chunk_outcomes=ordered_outcomes,
        total_tiles=sum(
            outcome.result.tile_count for outcome in ordered_outcomes if outcome.result
        ),
        any_failure_detected=any(
            outcome.failure_detected for outcome in ordered_outcomes
        ),
        all_chunks_eventually_succeeded=all(
            outcome.result is not None for outcome in ordered_outcomes
        ),
        total_recovery_seconds=sum(
            outcome.recovery_seconds or 0.0 for outcome in ordered_outcomes
        ),
    )


def _resolve_ready_chunk(
    pool: Pool,
    pending: dict[int, _PendingChunk],
    outcomes: dict[int, ChunkOutcome],
    chunk_index: int,
    max_retries: int,
) -> None:
    pending_chunk = pending.pop(chunk_index)

    try:
        result = pending_chunk.async_result.get()
    except Exception:
        pending_chunk.failure_detected = True
        if pending_chunk.failure_detected_at is None:
            pending_chunk.failure_detected_at = time.perf_counter()
        _retry_or_give_up(pool, pending, outcomes, pending_chunk, max_retries)
        return

    recovery_seconds = (
        time.perf_counter() - pending_chunk.failure_detected_at
        if pending_chunk.failure_detected_at is not None
        else None
    )
    outcomes[chunk_index] = ChunkOutcome(
        chunk_index=chunk_index,
        result=result,
        attempts=pending_chunk.attempts,
        failure_detected=pending_chunk.failure_detected,
        recovery_seconds=recovery_seconds,
    )


def _handle_timeout(
    pool: Pool,
    pending: dict[int, _PendingChunk],
    outcomes: dict[int, ChunkOutcome],
    chunk_index: int,
    max_retries: int,
) -> None:
    pending_chunk = pending.pop(chunk_index)
    pending_chunk.failure_detected = True
    if pending_chunk.failure_detected_at is None:
        pending_chunk.failure_detected_at = time.perf_counter()
    _retry_or_give_up(pool, pending, outcomes, pending_chunk, max_retries)


def _retry_or_give_up(
    pool: Pool,
    pending: dict[int, _PendingChunk],
    outcomes: dict[int, ChunkOutcome],
    pending_chunk: _PendingChunk,
    max_retries: int,
) -> None:
    if pending_chunk.attempts > max_retries:
        outcomes[pending_chunk.chunk_index] = ChunkOutcome(
            chunk_index=pending_chunk.chunk_index,
            result=None,
            attempts=pending_chunk.attempts,
            failure_detected=True,
            recovery_seconds=None,
        )
        return

    retry_task = dataclasses.replace(pending_chunk.task, inject_crash=False)
    pending[pending_chunk.chunk_index] = _PendingChunk(
        chunk_index=pending_chunk.chunk_index,
        task=retry_task,
        async_result=pool.apply_async(process_chunk, (retry_task,)),
        dispatched_at=time.perf_counter(),
        attempts=pending_chunk.attempts + 1,
        failure_detected=pending_chunk.failure_detected,
        failure_detected_at=pending_chunk.failure_detected_at,
    )
