"""Train the model the product serves, on the real historical dataset.

Calibrated XGBoost (the top of the locked model ladder): fit on the train
split with validation early stopping, isotonic calibration on the
validation split. The test split is not loaded into training at all.

    python scripts/forecast/build_historical_dataset.py   # once
    python scripts/models/train_production_model.py
"""

import json
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    save_production_model,
    train_production_model,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
MODEL_DIR = Path("ml/artifacts/production_model_v1")


def main() -> None:
    rows = load_dataset(DATASET_PATH)
    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    del rows

    model = train_production_model(train_rows, validation_rows)
    save_production_model(model, MODEL_DIR)
    print(json.dumps(model.metadata, indent=2))
    print(f"saved -> {MODEL_DIR}")


if __name__ == "__main__":
    main()
