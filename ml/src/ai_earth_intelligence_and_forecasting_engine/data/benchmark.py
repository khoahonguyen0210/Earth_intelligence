from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    FIRMSConfig,
    fetch_firms_sample,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import locate_tile
from ai_earth_intelligence_and_forecasting_engine.data.validation import (
    validate_observations,
)


@dataclass(frozen=True)
class PipelineBenchmarkResult:
    records_processed: int
    invalid_records: int
    records_outside_grid: int
    retrieval_time_s: float
    normalization_time_s: float
    validation_time_s: float
    feature_preparation_time_s: float
    total_time_s: float
    generated_at: str


def run_firms_pipeline_benchmark(
    config: FIRMSConfig,
    bbox: tuple[float, float, float, float],
    observed_date: date,
    raw_output_path: Path,
) -> PipelineBenchmarkResult:
    total_start = time.perf_counter()

    retrieval_start = time.perf_counter()
    raw_path = fetch_firms_sample(
        config=config,
        bbox=bbox,
        observed_date=observed_date,
        output_path=raw_output_path,
    )
    retrieval_time_s = time.perf_counter() - retrieval_start

    normalization_start = time.perf_counter()
    csv_text = raw_path.read_text(encoding="utf-8")
    records = parse_firms_records(csv_text)

    ingested_at = datetime.now(timezone.utc)
    observations = [
        normalize_firms_record(
            record=record,
            product=config.product,
            source_record_id=str(index),
            ingested_at=ingested_at,
        )
        for index, record in enumerate(records)
    ]
    normalization_time_s = time.perf_counter() - normalization_start

    validation_start = time.perf_counter()
    report = validate_observations(observations)
    validation_time_s = time.perf_counter() - validation_start

    feature_start = time.perf_counter()
    records_outside_grid = sum(
        1
        for observation in observations
        if locate_tile(observation.latitude, observation.longitude, bbox) is None
    )
    feature_preparation_time_s = time.perf_counter() - feature_start

    total_time_s = time.perf_counter() - total_start

    return PipelineBenchmarkResult(
        records_processed=len(observations),
        invalid_records=report.invalid_records,
        records_outside_grid=records_outside_grid,
        retrieval_time_s=retrieval_time_s,
        normalization_time_s=normalization_time_s,
        validation_time_s=validation_time_s,
        feature_preparation_time_s=feature_preparation_time_s,
        total_time_s=total_time_s,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def benchmark_result_to_dict(result: PipelineBenchmarkResult) -> dict[str, Any]:
    return {
        "records_processed": result.records_processed,
        "invalid_records": result.invalid_records,
        "records_outside_grid": result.records_outside_grid,
        "retrieval_time_s": result.retrieval_time_s,
        "normalization_time_s": result.normalization_time_s,
        "validation_time_s": result.validation_time_s,
        "feature_preparation_time_s": result.feature_preparation_time_s,
        "total_time_s": result.total_time_s,
        "generated_at": result.generated_at,
    }


def save_benchmark_result(result: PipelineBenchmarkResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(benchmark_result_to_dict(result), indent=2),
        encoding="utf-8",
    )

    return output_path
