import json
from datetime import date
from unittest.mock import patch

from ai_earth_intelligence_and_forecasting_engine.data.benchmark import (
    benchmark_result_to_dict,
    run_firms_pipeline_benchmark,
    save_benchmark_result,
)
from ai_earth_intelligence_and_forecasting_engine.data.firms import FIRMSConfig

SAMPLE_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence\n"
    "37.5,-119.5,2024-08-15,1001,n\n"
    "38.0,-120.0,2024-08-15,1002,h\n"
    "0.0,0.0,2024-08-15,1003,l\n"
    "10.0,10.0,2024-08-15,1004,n\n"
)


def _fake_fetch(config, bbox, observed_date, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(SAMPLE_CSV, encoding="utf-8")
    return output_path


def test_run_firms_pipeline_benchmark_counts_and_stages(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    raw_output_path = tmp_path / "firms.csv"

    with patch(
        "ai_earth_intelligence_and_forecasting_engine.data.benchmark.fetch_firms_sample",
        side_effect=_fake_fetch,
    ):
        result = run_firms_pipeline_benchmark(
            config=config,
            bbox=(-124.5, 32.5, -114.0, 42.0),
            observed_date=date(2024, 8, 15),
            raw_output_path=raw_output_path,
        )

    assert result.records_processed == 4
    assert result.invalid_records == 1
    assert result.records_outside_grid == 2

    assert result.retrieval_time_s >= 0
    assert result.normalization_time_s >= 0
    assert result.validation_time_s >= 0
    assert result.feature_preparation_time_s >= 0
    assert result.total_time_s >= (
        result.retrieval_time_s
        + result.normalization_time_s
        + result.validation_time_s
        + result.feature_preparation_time_s
    ) * 0.99  # allow tiny float/measurement slack


def test_benchmark_result_to_dict_is_json_serializable(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    raw_output_path = tmp_path / "firms.csv"

    with patch(
        "ai_earth_intelligence_and_forecasting_engine.data.benchmark.fetch_firms_sample",
        side_effect=_fake_fetch,
    ):
        result = run_firms_pipeline_benchmark(
            config=config,
            bbox=(-124.5, 32.5, -114.0, 42.0),
            observed_date=date(2024, 8, 15),
            raw_output_path=raw_output_path,
        )

    payload = benchmark_result_to_dict(result)
    json.dumps(payload)

    assert payload["records_processed"] == 4


def test_save_benchmark_result_roundtrip(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    raw_output_path = tmp_path / "firms.csv"

    with patch(
        "ai_earth_intelligence_and_forecasting_engine.data.benchmark.fetch_firms_sample",
        side_effect=_fake_fetch,
    ):
        result = run_firms_pipeline_benchmark(
            config=config,
            bbox=(-124.5, 32.5, -114.0, 42.0),
            observed_date=date(2024, 8, 15),
            raw_output_path=raw_output_path,
        )

    output_path = tmp_path / "benchmark.json"
    saved_path = save_benchmark_result(result, output_path)
    saved = json.loads(saved_path.read_text(encoding="utf-8"))

    assert saved["records_processed"] == 4
    assert saved["records_outside_grid"] == 2
