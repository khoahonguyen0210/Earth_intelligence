from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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
