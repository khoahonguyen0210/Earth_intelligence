from __future__ import annotations

import threading

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.serving.batching import (
    BatchPolicy,
    DynamicBatcher,
    Request,
    poisson_arrivals,
    run_load,
    summarize,
    sustained,
)


def doubling(features: np.ndarray) -> np.ndarray:
    return features[:, 0] * 2.0


def rows(first: int, count: int) -> np.ndarray:
    return np.arange(first, first + count, dtype=np.float64).reshape(count, 1)


class GatedScorer:
    def __init__(self):
        self.gate = threading.Event()
        self.calls: list[int] = []

    def __call__(self, features: np.ndarray) -> np.ndarray:
        self.gate.wait()
        self.calls.append(len(features))
        return doubling(features)


def test_each_request_gets_its_own_scores():
    batcher = DynamicBatcher(doubling, BatchPolicy(8, 0.05)).start()
    requests = [Request(rows(10 * number, 3), arrival=0.0) for number in range(5)]
    for request in requests:
        batcher.submit(request)
    batcher.stop()
    for number, request in enumerate(requests):
        np.testing.assert_array_equal(request.scores, rows(10 * number, 3)[:, 0] * 2)
        assert request.finished >= request.started > 0
    assert sum(batcher.batch_sizes) == 5


def test_queued_requests_are_scored_together_up_to_the_limit():
    scorer = GatedScorer()
    batcher = DynamicBatcher(scorer, BatchPolicy(3, 0.0)).start()
    first = Request(rows(0, 2), arrival=0.0)
    batcher.submit(first)
    while batcher._queue.qsize():
        pass
    queued = [Request(rows(100 + number, 2), arrival=0.0) for number in range(5)]
    for request in queued:
        batcher.submit(request)
    scorer.gate.set()
    batcher.stop()
    assert batcher.batch_sizes == [1, 3, 2]
    assert scorer.calls == [2, 6, 4]
    assert [request.batch_requests for request in queued] == [3, 3, 3, 2, 2]


def test_one_request_policy_never_batches():
    scorer = GatedScorer()
    batcher = DynamicBatcher(scorer, BatchPolicy(1, 0.0)).start()
    for number in range(4):
        batcher.submit(Request(rows(number, 1), arrival=0.0))
    scorer.gate.set()
    batcher.stop()
    assert batcher.batch_sizes == [1, 1, 1, 1]


def test_the_batcher_waits_for_more_requests():
    batcher = DynamicBatcher(doubling, BatchPolicy(4, 0.5)).start()
    batcher.submit(Request(rows(0, 1), arrival=0.0))
    batcher.submit(Request(rows(1, 1), arrival=0.0))
    batcher.stop()
    assert batcher.batch_sizes == [2]


def test_policies_reject_bad_limits():
    with pytest.raises(ValueError):
        BatchPolicy(0, 0.0)
    with pytest.raises(ValueError):
        BatchPolicy(1, -1.0)


def test_poisson_arrivals_are_repeatable_and_near_the_rate():
    first = poisson_arrivals(200.0, 20.0, seed=3)
    assert np.array_equal(first, poisson_arrivals(200.0, 20.0, seed=3))
    assert np.all(np.diff(first) > 0)
    assert first[-1] < 20.0
    assert 3600 < len(first) < 4400
    with pytest.raises(ValueError):
        poisson_arrivals(0.0, 1.0, seed=3)


def test_latency_counts_from_the_planned_arrival():
    clock = iter(np.arange(0.0, 100.0, 0.001)).__next__
    slept: list[float] = []
    batcher = DynamicBatcher(doubling, BatchPolicy(1, 0.0))
    batcher.start()
    requests, start = run_load(
        batcher,
        lambda number: rows(number, 2),
        np.array([0.0, 0.002]),
        clock=clock,
        sleep=slept.append,
    )
    assert [request.arrival - start for request in requests] == pytest.approx(
        [0.0, 0.002]
    )
    assert slept and all(delay > 0 for delay in slept)
    assert all(request.scores is not None for request in requests)


def test_summary_and_service_level():
    requests = []
    for number in range(100):
        request = Request(rows(number, 1), arrival=number * 0.01)
        request.finished = request.arrival + (0.2 if number < 2 else 0.002)
        request.batch_requests = 2
        requests.append(request)
    summary = summarize(requests, 0.0, 100.0, 1.0)
    assert summary["requests"] == 100
    assert summary["generated_rate"] == 100.0
    assert summary["p50_ms"] == pytest.approx(2.0)
    assert summary["max_ms"] == pytest.approx(200.0)
    assert summary["mean_batch_requests"] == 2.0
    assert sustained(summary, p99_limit_ms=250.0, share=0.95)
    assert not sustained(summary, p99_limit_ms=50.0, share=0.95)
    assert not sustained(summarize([], 0.0, 100.0, 1.0), 250.0, 0.95)
