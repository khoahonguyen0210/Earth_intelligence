from __future__ import annotations

from typing import Any

GPU_GAIN = 1.5
GPU_BATCH_GAIN = 2.0
CPU_BATCH_GAIN = 1.5
LOW_RATE_EXTRA_MS = 5.0
SCORE_TOLERANCE = 1e-5

Sweep = list[dict[str, Any]]


def highest_rate(rows: Sweep) -> float:
    return max((row["offered_rate"] for row in rows if row["sustained"]), default=0.0)


def lowest_rate_p50(rows: Sweep) -> float:
    return rows[0]["p50_ms"] if rows else float("inf")


def decisions(runs: dict[str, list[Sweep]], accuracy: dict[str, float]) -> dict:
    best = {
        name: [highest_rate(rows) for rows in repeats] for name, repeats in runs.items()
    }
    p50 = {
        name: [lowest_rate_p50(rows) for rows in repeats]
        for name, repeats in runs.items()
    }
    gpu_error = accuracy.get("cuda_vs_reference", float("inf"))
    gpu_ok = gpu_error <= SCORE_TOLERANCE
    result: dict[str, Any] = {
        "highest_sustained_rate": best,
        "p50_ms_at_lowest_rate": p50,
        "gpu_scores_within_tolerance": gpu_ok,
    }
    if best.get("gpu_single") and best.get("cpu_single"):
        result["gpu_instead_of_cpu"] = gpu_ok and min(
            best["gpu_single"]
        ) >= GPU_GAIN * max(best["cpu_single"])
    if best.get("gpu_batched") and best.get("gpu_single"):
        result["batching_on_gpu"] = (
            gpu_ok
            and min(best["gpu_batched"]) >= GPU_BATCH_GAIN * max(best["gpu_single"])
            and max(p50["gpu_batched"]) <= min(p50["gpu_single"]) + LOW_RATE_EXTRA_MS
        )
    if best.get("cpu_batched") and best.get("cpu_single"):
        result["batching_on_cpu"] = min(best["cpu_batched"]) >= CPU_BATCH_GAIN * max(
            best["cpu_single"]
        )
    return result
