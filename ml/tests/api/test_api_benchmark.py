import json

import pytest

from ai_earth_intelligence_and_forecasting_engine.api.benchmark import (
    api_benchmark_result_to_dict,
    latency_percentile,
    run_api_benchmark,
    save_api_benchmark_result,
)


def test_latency_percentile_uses_nearest_rank_over_ten_values():
    latencies = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    assert latency_percentile(latencies, 50) == 5
    assert latency_percentile(latencies, 95) == 10
    assert latency_percentile(latencies, 99) == 10


def test_latency_percentile_of_empty_sequence_is_zero():
    assert latency_percentile([], 50) == 0.0


def test_latency_percentile_of_single_value_is_that_value():
    assert latency_percentile([0.42], 99) == 0.42


def test_run_api_benchmark_with_all_successes_has_zero_error_rate():
    result = run_api_benchmark("POST /forecasts", lambda: None, request_count=20)

    assert result.request_count == 20
    assert result.error_count == 0
    assert result.error_rate == 0.0
    assert result.p50_latency_seconds >= 0
    assert result.p95_latency_seconds >= result.p50_latency_seconds
    assert result.p99_latency_seconds >= result.p95_latency_seconds
    assert result.throughput_requests_per_second > 0
    assert result.total_time_seconds >= 0


def test_run_api_benchmark_counts_errors_and_excludes_them_from_latency():
    calls = {"count": 0}

    def send_request():
        calls["count"] += 1
        if calls["count"] % 4 == 0:
            raise RuntimeError("simulated 5xx")

    result = run_api_benchmark("POST /forecasts", send_request, request_count=20)

    assert result.request_count == 20
    assert result.error_count == 5
    assert result.error_rate == pytest.approx(0.25)


def test_run_api_benchmark_with_all_errors_has_zero_latency_and_throughput():
    def always_fails():
        raise RuntimeError("connection refused")

    result = run_api_benchmark("POST /forecasts", always_fails, request_count=5)

    assert result.error_count == 5
    assert result.error_rate == 1.0
    assert result.p50_latency_seconds == 0.0
    assert result.throughput_requests_per_second == 0.0


def test_api_benchmark_result_to_dict_is_json_serializable():
    result = run_api_benchmark("POST /forecasts", lambda: None, request_count=3)

    payload = api_benchmark_result_to_dict(result)
    json.dumps(payload)

    assert payload["endpoint"] == "POST /forecasts"
    assert payload["request_count"] == 3
    assert payload["benchmark_version"] == "v1"


def test_save_api_benchmark_result_roundtrip(tmp_path):
    result = run_api_benchmark("POST /forecasts", lambda: None, request_count=3)

    output_path = tmp_path / "forecast_api_benchmark.json"
    saved_path = save_api_benchmark_result(result, output_path)
    saved = json.loads(saved_path.read_text(encoding="utf-8"))

    assert saved["request_count"] == 3
    assert saved["error_count"] == 0
