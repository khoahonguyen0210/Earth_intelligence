"""Live demo of the dataset builder against the real sample data.

Honesty note: we only have real historical data for a single real day
(2024-08-15, from the real FIRMS/ERA5-Land/geography samples already
fetched), which falls in the locked TEST split. To demonstrate the pipeline
assembles a dataset spanning all three splits, this script also computes
rows for a train-period and a validation-period cutoff -- those will
correctly show zero fire activity and no environmental data, because we
have not ingested any real historical data for 2019-2023. This is not a
full 6-year production dataset; it is a correctness demonstration of the
join/manifest logic against the one real day of data the project has
fetched so far.
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
    build_dataset_manifest,
    save_dataset,
    save_dataset_manifest,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

DATASET_OUTPUT_PATH = Path("data/processed/forecast/dataset_sample.csv")
MANIFEST_OUTPUT_PATH = Path("data/processed/forecast/dataset_manifest.json")

REAL_DATA_CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)
TRAIN_DEMO_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
VALIDATION_DEMO_CUTOFF = datetime(2023, 8, 15, 10, 0, tzinfo=timezone.utc)
CUTOFFS = [TRAIN_DEMO_CUTOFF, VALIDATION_DEMO_CUTOFF, REAL_DATA_CUTOFF]


def main() -> None:
    firms_config = load_firms_config()
    firms_csv = RAW_FIRMS_PATH.read_text(encoding="utf-8")
    firms_records = parse_firms_records(firms_csv)
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

    print(f"Observations: {len(observations)}, ERA5 records: {len(era5_records)}, "
          f"geography cells: {len(geography_cells)}")
    print(f"Grid: {len(cells)} cells, cutoffs: {[c.isoformat() for c in CUTOFFS]}")

    rows = build_dataset(observations, era5_records, geography_cells, cells, CUTOFFS)
    manifest = build_dataset_manifest(rows)

    save_dataset(rows, DATASET_OUTPUT_PATH)
    save_dataset_manifest(manifest, MANIFEST_OUTPUT_PATH)

    print(f"\nDataset version: {manifest.dataset_version}")
    print(f"Feature version: {manifest.feature_version}")
    print(f"Row counts: {manifest.row_counts}")
    print(f"Positive rates: {manifest.positive_rates}")
    print(f"Feature schema: {manifest.feature_schema}")

    print(f"\nSaved dataset to: {DATASET_OUTPUT_PATH}")
    print(f"Saved manifest to: {MANIFEST_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
