import json
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.forecast.fire_history_features import (
    FEATURE_DATASET_VERSION,
    compute_fire_history_features,
    save_fire_history_features,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
FEATURES_OUTPUT_PATH = Path("data/processed/forecast/fire_history_features_sample.csv")
METADATA_OUTPUT_PATH = Path(
    "data/processed/forecast/fire_history_features_sample_metadata.json"
)

CUTOFF = datetime(2024, 8, 16, 0, 0, tzinfo=timezone.utc)


def main() -> None:
    config = load_firms_config()
    csv_text = RAW_FIRMS_PATH.read_text(encoding="utf-8")
    records = parse_firms_records(csv_text)

    ingested_at = datetime.now(timezone.utc)
    observations = [
        normalize_firms_record(
            record=record,
            product=config.product,
            source_record_id=str(index),
            ingested_at=ingested_at,
        )
        for index, record in enumerate(records)
    ]

    cells = build_california_grid()

    print(f"Loaded {len(observations)} FIRMS observations")
    print(f"Grid: {len(cells)} cells")
    print(f"Cutoff: {CUTOFF.isoformat()}")

    feature_records = compute_fire_history_features(observations, cells, [CUTOFF])

    nonzero_24h = [r for r in feature_records if r.previous_24h_count > 0]
    nonzero_neighbor = [
        r for r in feature_records if r.neighboring_previous_24h_count > 0
    ]

    print(f"\nCells with previous_24h_count > 0: {len(nonzero_24h)}")
    print(
        f"Cells with neighboring_previous_24h_count > 0: {len(nonzero_neighbor)}"
    )

    print("\n--- 5 example cells with nonzero fire history ---")
    for record in nonzero_24h[:5]:
        print(
            f"  {record.tile_id}: 24h={record.previous_24h_count}, "
            f"72h={record.previous_72h_count}, 7d={record.previous_7d_count}, "
            f"30d={record.previous_30d_count}, "
            f"neighbor_24h={record.neighboring_previous_24h_count}"
        )

    save_fire_history_features(feature_records, FEATURES_OUTPUT_PATH)

    metadata = {
        "feature_dataset_version": FEATURE_DATASET_VERSION,
        "cutoff": CUTOFF.isoformat(),
        "cell_count": len(cells),
        "observation_count": len(observations),
        "cells_with_24h_activity": len(nonzero_24h),
        "cells_with_neighbor_activity": len(nonzero_neighbor),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    METADATA_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_OUTPUT_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nSaved features to: {FEATURES_OUTPUT_PATH}")
    print(f"Saved metadata to: {METADATA_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
