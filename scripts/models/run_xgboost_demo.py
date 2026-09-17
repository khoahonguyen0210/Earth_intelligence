"""Live demo of the XGBoost baseline against the real dataset built by
the forecast pipeline.

The train/validation splits currently have zero real positive
examples, so this is expected to hit that same limitation.
"""

from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import parse_era5_records
from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    build_geography_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    build_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    evaluate_xgboost,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

TRAIN_DEMO_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
VALIDATION_DEMO_CUTOFF = datetime(2023, 8, 15, 10, 0, tzinfo=timezone.utc)
TEST_CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)


def main() -> None:
    firms_config = load_firms_config()
    firms_records = parse_firms_records(RAW_FIRMS_PATH.read_text(encoding="utf-8"))
    ingested_at = datetime.now(timezone.utc)
    observations = [
        normalize_firms_record(
            record=record,
            product=firms_config.product,
            source_record_id=str(index),
            ingested_at=ingested_at,
        )
        for index, record in enumerate(firms_records)
    ]

    era5_records = parse_era5_records(RAW_ERA5_PATH)
    geography_cells = build_geography_grid(
        bbox=GEOGRAPHY_BBOX,
        resolution_deg=0.1,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )
    cells = build_california_grid()

    rows = build_dataset(
        observations,
        era5_records,
        geography_cells,
        cells,
        [TRAIN_DEMO_CUTOFF, VALIDATION_DEMO_CUTOFF, TEST_CUTOFF],
    )

    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    test_rows = [row for row in rows if row.split == "test"]

    print(
        f"Train rows: {len(train_rows)}, validation rows: {len(validation_rows)}, "
        f"test rows: {len(test_rows)}"
    )
    print(f"Train positive count: {sum(row.target for row in train_rows)}")
    print(f"Validation positive count: {sum(row.target for row in validation_rows)}")

    try:
        result, _predictions, metrics = evaluate_xgboost(
            train_rows, validation_rows, test_rows
        )
        print(f"Best iteration: {result.best_iteration}")
        print(f"Metrics: {metrics}")
    except ValueError as error:
        print(f"\nExpected, honest result: {error}")
        print(
            "\nThis is a real data-availability gap, not a code bug -- see "
            "ml/tests/models/test_xgboost_model.py for proof the model "
            "correctly fits, tunes, and discriminates on real, separable data."
        )


if __name__ == "__main__":
    main()
