"""The final ML benchmark, against the real historical
dataset (data/processed/historical_dataset_v1.csv), not the tiny
sample data scripts/models/run_final_benchmark.py used.

That earlier run predates the real historical dataset entirely (its
own docstring: "only climatology can currently succeed against real
data -- the training/validation splits have zero real positive
examples"). The real dataset has since been built
(scripts/forecast/build_historical_dataset.py) and already backs the
production model (scripts/models/train_production_model.py); this
script runs the same benchmark-v1-frozen comparison
(models/benchmark.py::run_baseline_benchmark, unchanged) against it,
producing the first real PR-AUC/ROC-AUC/Brier/log-loss/inference-time
comparison across all four locked models.

    python scripts/models/run_final_ml_benchmark.py
"""

from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.benchmark import (
    run_baseline_benchmark,
    save_benchmark_comparison,
    save_benchmark_table,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
BENCHMARK_OUTPUT_DIR = Path("ml/artifacts/final_ml_benchmark_v1")


def main() -> None:
    rows = load_dataset(DATASET_PATH)
    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    test_rows = [row for row in rows if row.split == "test"]
    del rows

    benchmark_rows = run_baseline_benchmark(
        train_rows,
        validation_rows,
        test_rows,
        experiment_prefix="final_ml_benchmark_v1",
    )

    save_benchmark_comparison(benchmark_rows, BENCHMARK_OUTPUT_DIR / "comparison.json")
    save_benchmark_table(benchmark_rows, BENCHMARK_OUTPUT_DIR / "comparison.csv")

    print(
        f"{'Model':<22}{'Succeeded':<11}{'PR-AUC':<10}{'ROC-AUC':<10}"
        f"{'Brier':<10}{'LogLoss':<10}{'Train(s)':<10}{'Infer(s)':<10}"
    )
    for row in benchmark_rows:
        def fmt(value: float | None) -> str:
            return f"{value:.4f}" if value is not None else "n/a"

        print(
            f"{row.model:<22}{str(row.succeeded):<11}{fmt(row.pr_auc):<10}"
            f"{fmt(row.roc_auc):<10}{fmt(row.brier_score):<10}"
            f"{fmt(row.log_loss):<10}{fmt(row.training_time_seconds):<10}"
            f"{fmt(row.inference_time_seconds):<10}"
        )
        if row.error:
            print(f"    -> {row.error}")

    print(f"\nSaved benchmark comparison to: {BENCHMARK_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
