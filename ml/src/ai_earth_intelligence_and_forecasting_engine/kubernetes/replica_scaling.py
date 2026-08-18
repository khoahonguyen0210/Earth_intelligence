from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import json

BENCHMARK_VERSION = "v1"

TERMINAL_STATUSES = ("SUCCEEDED", "FAILED")


@dataclass(frozen=True)
class ReplicaScalingTrialResult:
    replicas: int
    job_count: int
    total_wall_seconds: float
    throughput_jobs_per_second: float
    per_job_seconds: tuple[float, ...]
    status_counts: dict[str, int]


def run_replica_scaling_trial(
    replicas: int,
    job_count: int,
    submit_job: Callable[[], str],
    poll_job_status: Callable[[str], str],
    poll_interval_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> ReplicaScalingTrialResult:
    """Submits `job_count` identical jobs back-to-back (Task 6.5's Redis
    queue, not this function, is what actually load-balances them across
    however many backend/worker replicas are running) and polls every
    job until it reaches a terminal status, timing the whole batch.

    `submit_job`/`poll_job_status`/`sleep`/`now` are injected so this can
    be unit-tested against fakes -- the real caller
    (scripts/kubernetes/run_replica_scaling_benchmark.py) passes real
    HTTP calls against a real `kubectl scale`-d Deployment; this module
    only owns the timing/throughput arithmetic, the same split
    ml/.../api/benchmark.py already uses for the sequential API
    benchmark (Task 6.7).

    A job reaching FAILED still counts as a completed unit of work here,
    not an error: docs/clean-start-test.md's already-documented
    single-class training-data gap makes every real forecast request
    reach FAILED regardless of replica count, but it still exercises the
    full dequeue -> subprocess -> result pipeline this benchmark measures
    the throughput of.
    """
    start = now()
    job_ids = [submit_job() for _ in range(job_count)]

    per_job_start = {job_id: now() for job_id in job_ids}
    per_job_seconds: dict[str, float] = {}
    status_counts: dict[str, int] = {}
    pending = set(job_ids)

    while pending:
        for job_id in list(pending):
            status = poll_job_status(job_id)
            if status in TERMINAL_STATUSES:
                per_job_seconds[job_id] = now() - per_job_start[job_id]
                status_counts[status] = status_counts.get(status, 0) + 1
                pending.discard(job_id)
        if pending:
            sleep(poll_interval_seconds)

    total_wall_seconds = now() - start

    return ReplicaScalingTrialResult(
        replicas=replicas,
        job_count=job_count,
        total_wall_seconds=total_wall_seconds,
        throughput_jobs_per_second=(
            job_count / total_wall_seconds if total_wall_seconds > 0 else 0.0
        ),
        per_job_seconds=tuple(per_job_seconds[job_id] for job_id in job_ids),
        status_counts=status_counts,
    )


@dataclass(frozen=True)
class ReplicaScalingPoint:
    trial: ReplicaScalingTrialResult
    speedup: float
    efficiency: float


def compute_speedup_efficiency(
    trials: list[ReplicaScalingTrialResult],
) -> list[ReplicaScalingPoint]:
    """The handbook's own formulas (also used for the Task 9.3
    multi-worker benchmark, ml/.../distributed/scaling.py):
    speedup(n) = T1 / Tn, efficiency(n) = speedup(n) / n, against the
    first trial's (replicas=1) wall time as T1. `trials` is expected
    sorted by replica count ascending, replicas=1 first."""
    baseline_seconds = trials[0].total_wall_seconds

    points = []
    for trial in trials:
        speedup = (
            baseline_seconds / trial.total_wall_seconds
            if trial.total_wall_seconds > 0
            else 0.0
        )
        efficiency = speedup / trial.replicas if trial.replicas > 0 else 0.0
        points.append(
            ReplicaScalingPoint(trial=trial, speedup=speedup, efficiency=efficiency)
        )
    return points


def replica_scaling_point_to_dict(point: ReplicaScalingPoint) -> dict:
    return {
        **replica_scaling_trial_to_dict(point.trial),
        "speedup": point.speedup,
        "efficiency": point.efficiency,
    }


def replica_scaling_trial_to_dict(result: ReplicaScalingTrialResult) -> dict:
    return asdict(result)


def save_replica_scaling_results(
    results: list[ReplicaScalingTrialResult], output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "benchmark_version": BENCHMARK_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "trials": [replica_scaling_trial_to_dict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path
