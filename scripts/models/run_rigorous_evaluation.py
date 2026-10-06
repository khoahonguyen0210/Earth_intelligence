import csv
import json
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    SPATIAL_FOLDS,
    block_bootstrap,
    persistence_scores,
    spatial_fold,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    compute_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
    predict_xgboost,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
PREDICTIONS = {
    "climatology": "ml/artifacts/final_ml_benchmark_v1_climatology/predictions.csv",
    "logistic_regression": (
        "ml/artifacts/final_ml_benchmark_v1_logistic_regression/predictions.csv"
    ),
    "xgboost": "ml/artifacts/final_ml_benchmark_v1_xgboost/predictions.csv",
    "calibrated_xgboost": (
        "ml/artifacts/final_ml_benchmark_v1_calibrated_xgboost/predictions.csv"
    ),
}
OUTPUT_PATH = Path("data/processed/evaluation/rigorous_evaluation_v1.json")


def _load_predictions(path: str) -> dict[tuple[str, str], float]:
    with Path(path).open(encoding="utf-8") as handle:
        return {
            (record["tile_id"], record["cutoff"]): float(record["predicted_probability"])
            for record in csv.DictReader(handle)
        }


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

    keys = [(row.tile_id, row.cutoff.isoformat()) for row in test]
    y = np.array([row.target for row in test])
    groups = np.array([row.cutoff.isoformat() for row in test])

    scores: dict[str, np.ndarray] = {}
    for name, path in PREDICTIONS.items():
        predictions = _load_predictions(path)
        scores[name] = np.array([predictions[key] for key in keys])
    scores["persistence_24h"] = np.array(persistence_scores(test, "24h"))
    scores["persistence_7d"] = np.array(persistence_scores(test, "7d"))

    metric, difference = block_bootstrap(y, scores, groups, baseline="climatology")
    _, versus_persistence = block_bootstrap(
        y, scores, groups, baseline="persistence_24h"
    )

    fold_of = np.array([spatial_fold(row.tile_id) for row in test])
    full_model = fit_xgboost(train, validation)
    full = np.array(predict_xgboost(full_model, test))
    held_out = np.zeros(len(test))
    folds = []
    for fold in range(SPATIAL_FOLDS):
        model = fit_xgboost(
            [row for row in train if spatial_fold(row.tile_id) != fold],
            [row for row in validation if spatial_fold(row.tile_id) != fold],
        )
        mask = fold_of == fold
        held_out[mask] = predict_xgboost(model, [test[i] for i in np.flatnonzero(mask)])
        targets = y[mask].tolist()
        folds.append(
            {
                "fold": fold,
                "test_rows": int(mask.sum()),
                "test_fires": int(y[mask].sum()),
                "pr_auc_block_seen": round(
                    compute_metrics(targets, full[mask].tolist()).pr_auc, 4
                ),
                "pr_auc_block_hidden": round(
                    compute_metrics(targets, held_out[mask].tolist()).pr_auc, 4
                ),
            }
        )

    spatial_metric, spatial_difference = block_bootstrap(
        y, {"blocks_seen": full, "blocks_hidden": held_out}, groups, "blocks_seen"
    )

    report = {
        "test_rows": len(test),
        "test_fires": int(y.sum()),
        "test_cutoffs": len(np.unique(groups)),
        "bootstrap": {"samples": 1000, "unit": "forecast cutoff", "interval": "95%"},
        "pr_auc": {name: _interval(entry) for name, entry in metric.items()},
        "pr_auc_minus_climatology": {
            name: _interval(entry) for name, entry in difference.items()
        },
        "pr_auc_minus_persistence_24h": {
            name: _interval(entry) for name, entry in versus_persistence.items()
        },
        "spatial_holdout": {
            "block": "1 degree (10 x 10 cells)",
            "folds": folds,
            "pr_auc": {name: _interval(entry) for name, entry in spatial_metric.items()},
            "hidden_minus_seen": _interval(spatial_difference["blocks_hidden"]),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
