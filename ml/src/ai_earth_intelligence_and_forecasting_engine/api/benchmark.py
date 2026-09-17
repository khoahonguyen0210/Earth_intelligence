from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

BENCHMARK_VERSION = "v1"


@dataclass(frozen=True)
class ApiBenchmarkResult:
    endpoint: str
    request_count: int
    error_count: int
    error_rate: float
    p50_latency_seconds: float
    p95_latency_seconds: float
    p99_latency_seconds: float
    throughput_requests_per_second: float
    total_time_seconds: float
    generated_at: str


def latency_percentile(latencies: Sequence[float], percentile: float) -> float:
    if not latencies:
        return 0.0

    ordered = sorted(latencies)
    index = min(len(ordered) - 1, int(round(percentile / 100 * (len(ordered) - 1))))

    return ordered[index]


def run_api_benchmark(
    endpoint: str,
    send_request: Callable[[], None],
    request_count: int,
) -> ApiBenchmarkResult:
    latencies: list[float] = []
    error_count = 0

    total_start = time.perf_counter()
    for _ in range(request_count):
        request_start = time.perf_counter()
        try:
            send_request()
        except Exception:
            error_count += 1
        else:
            latencies.append(time.perf_counter() - request_start)
    total_time_seconds = time.perf_counter() - total_start

    successful = len(latencies)

    return ApiBenchmarkResult(
        endpoint=endpoint,
        request_count=request_count,
        error_count=error_count,
        error_rate=error_count / request_count if request_count else 0.0,
        p50_latency_seconds=latency_percentile(latencies, 50),
        p95_latency_seconds=latency_percentile(latencies, 95),
        p99_latency_seconds=latency_percentile(latencies, 99),
        throughput_requests_per_second=(
            successful / total_time_seconds if total_time_seconds > 0 else 0.0
        ),
        total_time_seconds=total_time_seconds,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def api_benchmark_result_to_dict(result: ApiBenchmarkResult) -> dict:
    return {"benchmark_version": BENCHMARK_VERSION, **asdict(result)}


def save_api_benchmark_result(result: ApiBenchmarkResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(api_benchmark_result_to_dict(result), indent=2),
        encoding="utf-8",
    )

    return output_path
