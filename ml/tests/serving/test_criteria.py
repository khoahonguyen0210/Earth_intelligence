from __future__ import annotations

from ai_earth_intelligence_and_forecasting_engine.serving.criteria import (
    decisions,
    highest_rate,
)


def sweep(highest: float, p50: float = 1.0) -> list[dict]:
    rates = [25.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0, 6400.0]
    rows = [
        {"offered_rate": rate, "sustained": rate <= highest, "p50_ms": p50}
        for rate in rates
        if rate <= highest * 2
    ]
    return rows


def runs(cpu: float, gpu: float, cpu_batched: float, gpu_batched: float) -> dict:
    return {
        "cpu_single": [sweep(cpu), sweep(cpu)],
        "gpu_single": [sweep(gpu, 1.5), sweep(gpu, 1.5)],
        "cpu_batched": [sweep(cpu_batched, 3.0), sweep(cpu_batched, 3.0)],
        "gpu_batched": [sweep(gpu_batched, 3.6), sweep(gpu_batched, 3.6)],
    }


def test_highest_rate_is_the_last_sustained_rate():
    assert highest_rate(sweep(800.0)) == 800.0
    assert highest_rate([]) == 0.0


def test_rules_use_the_gpu_score_error():
    accurate = {"cpu_vs_reference": 0.0, "cuda_vs_reference": 1e-6}
    result = decisions(runs(800, 1600, 3200, 6400), accurate)
    assert result["gpu_instead_of_cpu"]
    assert result["batching_on_gpu"]
    assert result["batching_on_cpu"]
    inaccurate = {"cpu_vs_reference": 0.0, "cuda_vs_reference": 3e-5}
    result = decisions(runs(800, 1600, 3200, 6400), inaccurate)
    assert not result["gpu_scores_within_tolerance"]
    assert not result["gpu_instead_of_cpu"]
    assert not result["batching_on_gpu"]
    assert result["batching_on_cpu"]


def test_gains_must_hold_in_every_run():
    accurate = {"cuda_vs_reference": 0.0}
    mixed = runs(800, 800, 3200, 6400)
    mixed["cpu_batched"][1] = sweep(800.0, 3.0)
    result = decisions(mixed, accurate)
    assert not result["gpu_instead_of_cpu"]
    assert result["batching_on_gpu"]
    assert not result["batching_on_cpu"]


def test_cpu_only_runs_give_cpu_decisions():
    result = decisions({"cpu_single": [sweep(800)], "cpu_batched": [sweep(3200)]}, {})
    assert result["batching_on_cpu"]
    assert "batching_on_gpu" not in result
