"""Train the PyTorch network on the locked splits and compare it with
XGBoost on the 2024 test year.

Same features, same train/validation/test split as the benchmark. The
network early-stops on validation PR-AUC; the test year is only scored.
Needs the research group: `uv sync --group research`.

    python scripts/research/run_neural_baseline.py
"""

import csv
import json
import time
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    block_bootstrap,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    compute_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.research.neural import (
    fit_neural,
    predict_neural,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
XGBOOST_PREDICTIONS = Path(
    "ml/artifacts/final_ml_benchmark_v1_xgboost/predictions.csv"
)
OUTPUT_PATH = Path("data/processed/evaluation/neural_baseline_v1.json")


def _interval(entry) -> dict[str, float]:
    return {
        "estimate": round(entry.estimate, 4),
        "low": round(entry.low, 4),
        "high": round(entry.high, 4),
    }


def main() -> None:
    rows = load_dataset(DATASET_PATH)
    train = [row for row in rows if row.split == "train"]
    validation = [row for row in rows if row.split == "validation"]
    test = [row for row in rows if row.split == "test"]
    del rows

    start = time.perf_counter()
    result = fit_neural(train, validation)
    training_seconds = time.perf_counter() - start
    neural = np.array(predict_neural(result, test))

    with XGBOOST_PREDICTIONS.open(encoding="utf-8") as handle:
        saved = {
            (record["tile_id"], record["cutoff"]): float(record["predicted_probability"])
            for record in csv.DictReader(handle)
        }
    xgboost = np.array([saved[(row.tile_id, row.cutoff.isoformat())] for row in test])

    y = np.array([row.target for row in test])
    groups = np.array([row.cutoff.isoformat() for row in test])
    metric, difference = block_bootstrap(
        y, {"xgboost": xgboost, "neural": neural}, groups, baseline="xgboost"
    )
    test_metrics = compute_metrics(y.tolist(), neural.tolist())

    report = {
        "network": "MLP 23 -> 64 -> 32 -> 1, ReLU, dropout 0.1",
        "best_epoch": result.best_epoch,
        "epochs_run": len(result.history),
        "validation_pr_auc": round(result.validation_pr_auc, 4),
        "training_seconds": round(training_seconds, 1),
        "test_pr_auc": {name: _interval(entry) for name, entry in metric.items()},
        "neural_minus_xgboost": _interval(difference["neural"]),
        "neural_test_roc_auc": round(test_metrics.roc_auc, 4),
        "history": result.history,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "history"}, indent=2))
    print(f"saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
