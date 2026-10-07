import argparse
import json
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.climatology import (
    fit_climatology,
    predict_climatology,
)
from ai_earth_intelligence_and_forecasting_engine.models.drift import (
    SERVING_DRIFT_FEATURES,
    drift_report,
    load_reference,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    block_bootstrap,
    persistence_scores,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    compute_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    load_production_model,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
MODEL_DIR = Path("ml/artifacts/production_model_v1")


def _interval(entry) -> dict[str, float]:
    return {
        "estimate": round(entry.estimate, 4),
        "low": round(entry.low, 4),
        "high": round(entry.high, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    season = parser.parse_args().season

    train = [row for row in load_dataset(DATASET_PATH) if row.split == "train"]
    rows = load_dataset(Path(f"data/processed/historical_dataset_{season}.csv"))
    model = load_production_model(MODEL_DIR)

    y = np.array([row.target for row in rows])
    groups = np.array([row.cutoff.isoformat() for row in rows])
    scores = {
        "climatology": np.array(predict_climatology(fit_climatology(train), rows)),
        "persistence_24h": np.array(persistence_scores(rows, "24h")),
        "persistence_7d": np.array(persistence_scores(rows, "7d")),
        "served_model": np.array(predict_calibrated(model.calibrated, rows)),
    }
    metric, versus_persistence = block_bootstrap(
        y, scores, groups, baseline="persistence_24h"
    )
    _, versus_climatology = block_bootstrap(y, scores, groups, baseline="climatology")
    served_metrics = compute_metrics(y.tolist(), scores["served_model"].tolist())

    reference = load_reference(MODEL_DIR)
    drift = (
        drift_report(reference, rows, SERVING_DRIFT_FEATURES) if reference else None
    )

    report = {
        "season": season,
        "model_version": model.metadata["model_version"],
        "model_trained_on": {
            "train": model.metadata["train"]["last_cutoff"],
            "validation": model.metadata["validation"]["last_cutoff"],
        },
        "rows": len(rows),
        "fires": int(y.sum()),
        "cutoffs": len(set(groups.tolist())),
        "pr_auc": {name: _interval(entry) for name, entry in metric.items()},
        "served_minus_persistence_24h": _interval(
            versus_persistence["served_model"]
        ),
        "served_minus_climatology": _interval(versus_climatology["served_model"]),
        "served_roc_auc": round(served_metrics.roc_auc, 4),
        "served_brier": round(served_metrics.brier_score, 6),
        "input_drift_vs_training": drift,
    }
    out = Path(f"data/processed/evaluation/new_season_{season}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
