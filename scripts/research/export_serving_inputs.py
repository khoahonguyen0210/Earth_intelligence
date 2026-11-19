import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xgboost

from ai_earth_intelligence_and_forecasting_engine.earth2.portable import (
    export_model,
    feature_matrix,
    predict,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    load_production_model,
)

DATASET = Path("data/processed/historical_dataset_2025.csv")
MODEL_DIR = Path("ml/artifacts/production_model_v1")
CUTOFFS = (
    datetime(2025, 8, 3, 10, tzinfo=timezone.utc),
    datetime(2025, 8, 10, 10, tzinfo=timezone.utc),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("ml/artifacts/serving_inputs")
    )
    arguments = parser.parse_args()

    rows = [row for row in load_dataset(DATASET) if row.cutoff in CUTOFFS]
    model = export_model(load_production_model(MODEL_DIR).calibrated)
    features = feature_matrix(model, rows).astype(np.float32)
    reference = predict(model, rows)

    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "model.json").write_text(json.dumps(model), encoding="utf-8")
    np.save(output / "features.npy", features)
    np.save(output / "reference.npy", reference)
    (output / "metadata.json").write_text(
        json.dumps(
            {
                "dataset": DATASET.as_posix(),
                "cutoffs": [cutoff.isoformat() for cutoff in CUTOFFS],
                "rows": len(rows),
                "features": features.shape[1],
                "trees": model["best_iteration"] + 1,
                "xgboost": xgboost.__version__,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"saved {features.shape[0]} rows of {features.shape[1]} features")


if __name__ == "__main__":
    main()
