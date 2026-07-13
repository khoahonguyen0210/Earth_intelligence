import json
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import parse_era5_records
from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.forecast.environmental_features import (
    FEATURE_DATASET_VERSION,
    compute_environmental_features,
    save_environmental_features,
)

RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
FEATURES_OUTPUT_PATH = Path(
    "data/processed/forecast/environmental_features_sample.csv"
)
METADATA_OUTPUT_PATH = Path(
    "data/processed/forecast/environmental_features_sample_metadata.json"
)

# The real ERA5-Land sample (Task 1.4) was fetched for 2024-08-15T10:00 UTC.
# A cutoff at that same hour makes every cell that has an ERA5 grid point
# cutoff-compatible.
CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)


def main() -> None:
    era5_records = parse_era5_records(RAW_ERA5_PATH)
    cells = build_california_grid()

    print(f"Loaded {len(era5_records)} ERA5-Land records")
    print(f"Grid: {len(cells)} cells")
    print(f"Cutoff: {CUTOFF.isoformat()}")

    feature_records = compute_environmental_features(era5_records, cells, [CUTOFF])

    with_data = [r for r in feature_records if r.temperature_2m is not None]
    without_data = [r for r in feature_records if r.temperature_2m is None]

    print(f"\nCells with environmental data: {len(with_data)}")
    print(f"Cells without environmental data (no ERA5 point / ocean): {len(without_data)}")

    print("\n--- 5 example cells with environmental data ---")
    for record in with_data[:5]:
        print(
            f"  {record.tile_id}: temp={record.temperature_2m:.1f}K, "
            f"precip={record.total_precipitation:.5f}, "
            f"u={record.u_wind_10m:.2f}, v={record.v_wind_10m:.2f}, "
            f"rh={record.relative_humidity:.1f}%"
        )

    save_environmental_features(feature_records, FEATURES_OUTPUT_PATH)

    metadata = {
        "feature_dataset_version": FEATURE_DATASET_VERSION,
        "cutoff": CUTOFF.isoformat(),
        "cell_count": len(cells),
        "era5_record_count": len(era5_records),
        "cells_with_data": len(with_data),
        "cells_without_data": len(without_data),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    METADATA_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_OUTPUT_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nSaved features to: {FEATURES_OUTPUT_PATH}")
    print(f"Saved metadata to: {METADATA_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
