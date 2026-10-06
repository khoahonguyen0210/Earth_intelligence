from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.ablation import (
    AblationVariant,
    run_geography_ablation,
    run_weather_ablation,
    save_ablation_result,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
OUTPUT_DIR = Path("ml/artifacts/final_ablation_benchmark_v1")


def _print_variant(variant: AblationVariant) -> None:
    def fmt(value: float | None) -> str:
        return f"{value:.4f}" if value is not None else "n/a"

    m = variant.metrics
    print(
        f"{variant.name:<38}{str(variant.succeeded):<11}"
        f"{fmt(m.pr_auc if m else None):<10}{fmt(m.roc_auc if m else None):<10}"
        f"{fmt(m.brier_score if m else None):<10}{fmt(m.log_loss if m else None):<10}"
    )
    if variant.error:
        print(f"    -> {variant.error}")


def main() -> None:
    rows = load_dataset(DATASET_PATH)
    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    test_rows = [row for row in rows if row.split == "test"]
    del rows

    weather_result = run_weather_ablation(train_rows, validation_rows, test_rows)
    geography_result = run_geography_ablation(train_rows, validation_rows, test_rows)

    save_ablation_result(weather_result, OUTPUT_DIR / "weather_ablation.json")
    save_ablation_result(geography_result, OUTPUT_DIR / "geography_ablation.json")

    print(f"{'Variant':<38}{'Succeeded':<11}{'PR-AUC':<10}{'ROC-AUC':<10}{'Brier':<10}{'LogLoss':<10}")
    _print_variant(weather_result.baseline)
    _print_variant(weather_result.candidate)
    _print_variant(geography_result.candidate)

    print(
        f"\nweather delta   (fire_history -> +weather):    "
        f"PR-AUC {weather_result.pr_auc_delta:+.4f}  ROC-AUC {weather_result.roc_auc_delta:+.4f}"
    )
    print(
        f"geography delta (+weather -> +weather+geography): "
        f"PR-AUC {geography_result.pr_auc_delta:+.4f}  ROC-AUC {geography_result.roc_auc_delta:+.4f}"
    )
    print(f"\nSaved ablation results to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
