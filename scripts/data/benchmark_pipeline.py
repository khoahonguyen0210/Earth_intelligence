from datetime import date
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.benchmark import (
    benchmark_result_to_dict,
    run_firms_pipeline_benchmark,
    save_benchmark_result,
)
from ai_earth_intelligence_and_forecasting_engine.data.firms import load_firms_config


def main() -> None:
    config = load_firms_config()

    # Same fixed historical slice used by the other Phase 1 adapters.
    bbox = (-124.5, 32.5, -114.0, 42.0)
    observed_date = date(2024, 8, 15)

    raw_output_path = Path("data/raw/firms/firms_sample.csv")
    benchmark_output_path = Path("data/processed/benchmark/pipeline_benchmark.json")

    result = run_firms_pipeline_benchmark(
        config=config,
        bbox=bbox,
        observed_date=observed_date,
        raw_output_path=raw_output_path,
    )

    save_benchmark_result(result, benchmark_output_path)

    for key, value in benchmark_result_to_dict(result).items():
        print(f"{key}: {value}")

    print(f"Saved benchmark result to: {benchmark_output_path}")


if __name__ == "__main__":
    main()
