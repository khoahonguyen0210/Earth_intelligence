import json
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    build_geography_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.forecast.geography_features import (
    FEATURE_DATASET_VERSION,
    compute_geography_features,
    save_geography_features,
)

DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")
FEATURES_OUTPUT_PATH = Path("data/processed/forecast/geography_features_sample.csv")
METADATA_OUTPUT_PATH = Path(
    "data/processed/forecast/geography_features_sample_metadata.json"
)

# Same Sierra Nevada foothills sample bbox used across the other feature
# demo scripts, so results stay comparable.
BBOX = (-119.8, 37.2, -119.4, 37.6)
RESOLUTION_DEG = 0.1


def main() -> None:
    geography_cells = build_geography_grid(
        bbox=BBOX,
        resolution_deg=RESOLUTION_DEG,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )
    cells = build_california_grid(bbox=BBOX, resolution_deg=RESOLUTION_DEG)

    print(f"Loaded {len(geography_cells)} geography grid cells")
    print(f"Forecast grid: {len(cells)} cells")

    feature_records = compute_geography_features(
        geography_cells, cells, bbox=BBOX, resolution_deg=RESOLUTION_DEG
    )

    with_data = [r for r in feature_records if r.elevation_m is not None]
    without_data = [r for r in feature_records if r.elevation_m is None]

    print(f"\nCells with geography data: {len(with_data)}")
    print(f"Cells without geography data: {len(without_data)}")

    print("\n--- 5 example cells ---")
    for record in with_data[:5]:
        print(
            f"  {record.tile_id}: elevation={record.elevation_m:.1f}m, "
            f"slope={record.slope_deg:.1f}deg, "
            f"land_cover_class={record.land_cover_class}"
        )

    save_geography_features(feature_records, FEATURES_OUTPUT_PATH)

    metadata = {
        "feature_dataset_version": FEATURE_DATASET_VERSION,
        "bbox": list(BBOX),
        "cell_count": len(cells),
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
