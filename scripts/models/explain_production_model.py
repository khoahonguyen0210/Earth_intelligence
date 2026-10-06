import json
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.explain import (
    Contributions,
    compute_contributions,
    mean_absolute_importance,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    load_production_model,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
MODEL_DIR = Path("ml/artifacts/production_model_v1")
OUTPUT_PATH = Path("data/processed/explainability/shap_test_2024.json")


def _importance(contributions: Contributions) -> list[dict[str, float | str]]:
    return [
        {
            "feature": entry.feature,
            "mean_abs_contribution": round(entry.contribution, 4),
        }
        for entry in mean_absolute_importance(contributions)
    ]


def main() -> None:
    test_rows = [row for row in load_dataset(DATASET_PATH) if row.split == "test"]
    model = load_production_model(MODEL_DIR)
    contributions = compute_contributions(model.calibrated, test_rows)

    positive = np.array([row.target == 1 for row in test_rows])
    on_fires = Contributions(
        features=contributions.features,
        values=contributions.values[positive],
        bias=contributions.bias[positive],
    )

    report = {
        "model_version": model.metadata["model_version"],
        "method": "xgboost_tree_shap",
        "units": "log_odds",
        "test_rows": len(test_rows),
        "test_fire_rows": int(positive.sum()),
        "expected_log_odds": round(float(contributions.bias[0]), 4),
        "all_rows": _importance(contributions),
        "fire_rows": _importance(on_fires),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
