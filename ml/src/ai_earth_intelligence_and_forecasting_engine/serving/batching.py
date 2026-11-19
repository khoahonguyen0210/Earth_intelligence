from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

Scorer = Callable[[np.ndarray], np.ndarray]
Clock = Callable[[], float]


@dataclass
class Request:
    features: np.ndarray
    arrival: float
    started: float = 0.0
    finished: float = 0.0
    batch_requests: int = 0
    scores: np.ndarray | None = None

    @property
    def latency(self) -> float:
        return self.finished - self.arrival


@dataclass(frozen=True)
class BatchPolicy:
    max_requests: int = 1
    max_wait_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if self.max_wait_seconds < 0:
            raise ValueError("max_wait_seconds cannot be negative")


class DynamicBatcher:
    def __init__(
        self,
        scorer: Scorer,
        policy: BatchPolicy,
        clock: Clock = time.perf_counter,
    ):
        self.scorer = scorer
        self.policy = policy
        self.clock = clock
        self.batch_sizes: list[int] = []
        self._queue: queue.Queue[Request | None] = queue.Queue()
        self._stopping = False
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> DynamicBatcher:
        self._thread.start()
        return self

    def submit(self, request: Request) -> None:
        self._queue.put(request)

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join()

    def _collect(self) -> list[Request]:
        first = self._queue.get()
        if first is None:
            self._stopping = True
            return []
        batch = [first]
        deadline = self.clock() + self.policy.max_wait_seconds
        while len(batch) < self.policy.max_requests:
            remaining = deadline - self.clock()
            try:
                item = (
                    self._queue.get(timeout=remaining)
                    if remaining > 0
                    else self._queue.get_nowait()
                )
            except queue.Empty:
                break
            if item is None:
                self._stopping = True
                break
            batch.append(item)
        return batch

    def _serve(self) -> None:
        while not self._stopping:
            batch = self._collect()
            if not batch:
                continue
            started = self.clock()
            scores = self.scorer(np.concatenate([item.features for item in batch]))
            finished = self.clock()
            offset = 0
            for item in batch:
                count = len(item.features)
                item.scores = scores[offset : offset + count]
                item.started = started
                item.finished = finished
                item.batch_requests = len(batch)
                offset += count
            self.batch_sizes.append(len(batch))


def poisson_arrivals(rate: float, duration: float, seed: int) -> np.ndarray:
    if rate <= 0 or duration <= 0:
        raise ValueError("rate and duration must be positive")
    generator = np.random.default_rng(seed)
    count = int(rate * duration * 1.5) + 16
    times = np.cumsum(generator.exponential(1.0 / rate, count))
    while times[-1] < duration:
        more = np.cumsum(generator.exponential(1.0 / rate, count)) + times[-1]
        times = np.concatenate([times, more])
    return times[times < duration]


def run_load(
    batcher: DynamicBatcher,
    features: Callable[[int], np.ndarray],
    arrivals: np.ndarray,
    clock: Clock = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[Request], float]:
    start = clock() + 0.05
    requests = []
    for number, offset in enumerate(arrivals):
        arrival = start + float(offset)
        delay = arrival - clock()
        if delay > 0:
            sleep(delay)
        request = Request(features=features(number), arrival=arrival)
        batcher.submit(request)
        requests.append(request)
    batcher.stop()
    return requests, start


def summarize(
    requests: list[Request], start: float, rate: float, duration: float
) -> dict[str, Any]:
    if not requests:
        return {"offered_rate": rate, "requests": 0}
    latencies = np.array([item.latency for item in requests]) * 1000.0
    finished = max(item.finished for item in requests)
    sizes = np.array([item.batch_requests for item in requests])
    return {
        "offered_rate": rate,
        "duration_seconds": duration,
        "requests": len(requests),
        "generated_rate": round(len(requests) / duration, 2),
        "achieved_rate": round(len(requests) / (finished - start), 2),
        "p50_ms": round(float(np.percentile(latencies, 50)), 3),
        "p90_ms": round(float(np.percentile(latencies, 90)), 3),
        "p99_ms": round(float(np.percentile(latencies, 99)), 3),
        "max_ms": round(float(latencies.max()), 3),
        "mean_batch_requests": round(float(sizes.mean()), 2),
    }


def sustained(summary: dict[str, Any], p99_limit_ms: float, share: float) -> bool:
    if not summary.get("requests"):
        return False
    return (
        summary["p99_ms"] <= p99_limit_ms
        and summary["achieved_rate"] >= share * summary["generated_rate"]
    )
