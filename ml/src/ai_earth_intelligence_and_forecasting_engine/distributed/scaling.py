from __future__ import annotations

from dataclasses import dataclass

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    DistributedRunResult,
    RunContext,
    run_distributed_inference,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    DistributedWorkload,
)

# Task 9.3 (Execution Handbook Phase 9): the handbook's own fixed worker
# counts.
WORKER_COUNTS: tuple[int, ...] = (1, 2, 4, 8)


@dataclass(frozen=True)
class ScalingPoint:
    result: DistributedRunResult
    speedup: float
    efficiency: float


def run_scaling_benchmark(
    workload: DistributedWorkload,
    context: RunContext,
    worker_counts: tuple[int, ...] = WORKER_COUNTS,
) -> list[ScalingPoint]:
    """Task 9.3: runs Task 9.2's exact same implementation
    (run_distributed_inference) at each worker count in worker_counts,
    against one shared RunContext (the same loaded data and the same
    fitted model for every point -- see RunContext's own docstring for
    why that is what makes "keep workload/data/model fixed" literally
    true here, not just nominally true). The first worker count's wall
    time is T1; every point's speedup/efficiency (the handbook's own
    formulas) are computed against it, including the first point itself
    (speedup 1.0, efficiency 1.0/requested_workers)."""
    if not worker_counts:
        raise ValueError("worker_counts must not be empty")

    results = [
        run_distributed_inference(workload, num_workers, context)
        for num_workers in worker_counts
    ]

    baseline_seconds = results[0].wall_seconds

    return [_scaling_point(baseline_seconds, result) for result in results]


def _scaling_point(
    baseline_seconds: float, result: DistributedRunResult
) -> ScalingPoint:
    speedup = (
        baseline_seconds / result.wall_seconds
        if result.wall_seconds > 0
        else float("inf")
    )
    efficiency = speedup / result.requested_workers

    return ScalingPoint(result=result, speedup=speedup, efficiency=efficiency)
