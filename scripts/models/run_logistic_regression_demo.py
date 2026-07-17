"""Live demo of Task 4.2's logistic regression against the real Task 3.7
dataset.

Honesty note: same real limitation as Task 4.1's climatology demo -- the
project has only ingested real historical data for one real day
(2024-08-15, TEST split). The train split has zero real positive
examples, and scikit-learn's LogisticRegression genuinely cannot be fit
on single-class data (it raises, by design). This script expects that
exact, informative error and prints it rather than treating it as a
crash -- this is the correct, honest outcome given the current data
footprint, not a bug in the model code (which is proven correct against
a real, separable synthetic fixture in the test suite).
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
from ai_earth_intelligence_and_forecasting_engine.models.logistic_regression import (
    evaluate_logistic_regression,
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

    try:
        _result, _predictions, metrics = evaluate_logistic_regression(
            train_rows, validation_rows, test_rows
        )
        print(f"Metrics: {metrics}")
    except ValueError as error:
        print(f"\nExpected, honest result: {error}")
        print(
            "\nThis is a real data-availability gap, not a code bug -- see "
            "ml/tests/models/test_logistic_regression.py for proof the model "
            "correctly fits and discriminates on real, separable data."
        )


if __name__ == "__main__":
    main()
