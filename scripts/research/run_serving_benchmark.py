import argparse
import json
import os
import platform
import time
from pathlib import Path

import numpy as np
import xgboost

from ai_earth_intelligence_and_forecasting_engine.earth2.gpu_monitor import (
    GpuMonitor,
    nvml_reader,
)
from ai_earth_intelligence_and_forecasting_engine.serving.batching import (
    BatchPolicy,
    DynamicBatcher,
    poisson_arrivals,
    run_load,
    summarize,
    sustained,
)
from ai_earth_intelligence_and_forecasting_engine.serving.criteria import (
    decisions,
)
from ai_earth_intelligence_and_forecasting_engine.serving.scorer import (
    PortableScorer,
)

ROWS_PER_REQUEST = 256
RATES = (25, 50, 100, 200, 400, 800, 1600, 3200, 6400)
DURATION_SECONDS = 10.0
P99_LIMIT_MS = 100.0
ACHIEVED_SHARE = 0.95
SERVICE_REQUESTS = (1, 2, 4, 8, 16, 32, 64)
SETUPS = {
    "cpu_single": ("cpu", BatchPolicy(1, 0.0)),
    "gpu_single": ("cuda", BatchPolicy(1, 0.0)),
    "cpu_batched": ("cpu", BatchPolicy(64, 0.002)),
    "gpu_batched": ("cuda", BatchPolicy(64, 0.002)),
}


def load_inputs(directory: Path):
    model = json.loads((directory / "model.json").read_text(encoding="utf-8"))
    return (
        model,
        np.load(directory / "features.npy"),
        np.load(directory / "reference.npy"),
    )


def request_starts(rows: int, count: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, rows - ROWS_PER_REQUEST, count)


def service_times(scorer, features: np.ndarray) -> list[dict]:
    results = []
    for requests in SERVICE_REQUESTS:
        rows = features[: requests * ROWS_PER_REQUEST]
        for _ in range(3):
            scorer(rows)
        times = []
        for _ in range(20):
            started = time.perf_counter()
            scorer(rows)
            times.append((time.perf_counter() - started) * 1000.0)
        results.append(
            {
                "requests": requests,
                "rows": len(rows),
                "median_ms": round(float(np.median(times)), 3),
                "p90_ms": round(float(np.percentile(times, 90)), 3),
            }
        )
    return results


def sweep(
    scorer, device: str, policy: BatchPolicy, features, reference, rates, duration, seed
) -> list[dict]:
    rows = []
    for rate in rates:
        arrivals = poisson_arrivals(rate, duration, seed + int(rate))
        starts = request_starts(len(features), len(arrivals), seed + int(rate))
        batcher = DynamicBatcher(scorer, policy).start()
        reader = nvml_reader(0) if device == "cuda" else None
        monitor = GpuMonitor(reader)
        with monitor:
            requests, start = run_load(
                batcher,
                lambda number: features[
                    starts[number] : starts[number] + ROWS_PER_REQUEST
                ],
                arrivals,
            )
        summary = summarize(requests, start, rate, duration)
        summary["max_score_error"] = float(
            max(
                np.max(
                    np.abs(
                        item.scores
                        - reference[starts[number] : starts[number] + ROWS_PER_REQUEST]
                    )
                )
                for number, item in enumerate(requests)
            )
        )
        summary["sustained"] = sustained(summary, P99_LIMIT_MS, ACHIEVED_SHARE)
        summary["gpu_activity"] = monitor.summary()
        rows.append(summary)
        print(
            f"  {rate:6} req/s  achieved {summary['achieved_rate']:8.1f}  "
            f"p50 {summary['p50_ms']:9.2f} ms  p99 {summary['p99_ms']:9.2f} ms  "
            f"batch {summary['mean_batch_requests']:5.1f}  ok={summary['sustained']}",
            flush=True,
        )
        if not summary["sustained"]:
            break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs", type=Path, default=Path("ml/artifacts/serving_inputs")
    )
    parser.add_argument("--output", type=Path, default=Path("ml/artifacts/serving"))
    parser.add_argument("--setups", nargs="+", default=list(SETUPS))
    parser.add_argument("--rates", nargs="+", type=float, default=list(RATES))
    parser.add_argument("--duration", type=float, default=DURATION_SECONDS)
    parser.add_argument("--repeats", type=int, default=2)
    arguments = parser.parse_args()

    model, features, reference = load_inputs(arguments.inputs)
    threads = os.cpu_count() or 1
    devices = sorted({SETUPS[name][0] for name in arguments.setups})
    scorers = {device: PortableScorer(model, device, threads) for device in devices}

    accuracy = {
        f"{device}_vs_reference": float(np.max(np.abs(scorer(features) - reference)))
        for device, scorer in scorers.items()
    }
    print("accuracy", accuracy, flush=True)
    service = {
        device: service_times(scorer, features) for device, scorer in scorers.items()
    }
    print("service times", json.dumps(service), flush=True)

    runs: dict[str, list[list[dict]]] = {name: [] for name in arguments.setups}
    for repeat in range(arguments.repeats):
        order = arguments.setups if repeat % 2 == 0 else arguments.setups[::-1]
        for name in order:
            device, policy = SETUPS[name]
            print(f"{name}, repeat {repeat + 1}", flush=True)
            runs[name].append(
                sweep(
                    scorers[device],
                    device,
                    policy,
                    features,
                    reference,
                    arguments.rates,
                    arguments.duration,
                    1000 * (repeat + 1),
                )
            )

    result = {
        "environment": {
            "xgboost": xgboost.__version__,
            "python": platform.python_version(),
            "cpu_count": threads,
            "gpu": _gpu_name() if "cuda" in devices else None,
        },
        "rows_per_request": ROWS_PER_REQUEST,
        "duration_seconds": arguments.duration,
        "p99_limit_ms": P99_LIMIT_MS,
        "achieved_share": ACHIEVED_SHARE,
        "policies": {
            name: {
                "device": SETUPS[name][0],
                "max_requests": SETUPS[name][1].max_requests,
                "max_wait_ms": SETUPS[name][1].max_wait_seconds * 1000,
            }
            for name in arguments.setups
        },
        "accuracy": accuracy,
        "service_times": service,
        "runs": runs,
        "decisions": decisions(runs, accuracy),
    }
    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "serving_benchmark.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result["decisions"], indent=2))


def _gpu_name() -> str:
    import torch

    return torch.cuda.get_device_name(0)


if __name__ == "__main__":
    main()
