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
