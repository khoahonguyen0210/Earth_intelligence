import json
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.forecast.labels import (
    LABEL_DATASET_VERSION,
    construct_labels,
    save_labels,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
LABELS_OUTPUT_PATH = Path("data/processed/forecast/labels_sample.csv")
METADATA_OUTPUT_PATH = Path("data/processed/forecast/labels_sample_metadata.json")

CUTOFF = datetime(2024, 8, 15, 0, 0, tzinfo=timezone.utc)


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

    label_records = construct_labels(observations, cells, [CUTOFF])

    positive = [record for record in label_records if record.target == 1]
    negative = [record for record in label_records if record.target == 0]

    print(f"\nPositive labels: {len(positive)}")
    print(f"Negative labels: {len(negative)}")

    print("\n--- Manual inspection: 5 positive examples ---")
    for record in positive[:5]:
        print(
            f"  {record.tile_id} @ {record.cutoff.isoformat()} -> "
            f"target={record.target}, "
            f"{len(record.qualifying_observation_ids)} qualifying observation(s)"
        )

    print("\n--- Manual inspection: 5 negative examples ---")
    for record in negative[:5]:
        print(
            f"  {record.tile_id} @ {record.cutoff.isoformat()} -> "
            f"target={record.target}"
        )

    save_labels(label_records, LABELS_OUTPUT_PATH)

    metadata = {
        "label_dataset_version": LABEL_DATASET_VERSION,
        "cutoff": CUTOFF.isoformat(),
        "cell_count": len(cells),
        "observation_count": len(observations),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    METADATA_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_OUTPUT_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nSaved labels to: {LABELS_OUTPUT_PATH}")
    print(f"Saved metadata to: {METADATA_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
