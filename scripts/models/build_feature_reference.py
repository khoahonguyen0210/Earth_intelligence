"""Save the training feature distribution next to the served model, and
measure how far the validation and test years drift from it.

Every forecast then compares its own input rows against this reference
and reports the population stability index per feature.

    python scripts/models/build_feature_reference.py
"""

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.drift import (
    SERVING_DRIFT_FEATURES,
    WEATHER_FEATURES,
    build_reference,
    drift_report,
    save_reference,
)

FIRE_COUNTS = (
    "previous_24h_count",
    "previous_72h_count",
    "previous_7d_count",
    "previous_30d_count",
    "neighboring_previous_24h_count",
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
MODEL_DIR = Path("ml/artifacts/production_model_v1")
OUTPUT_PATH = Path("data/processed/evaluation/drift_v1.json")


def main() -> None:
    rows = load_dataset(DATASET_PATH)
    by_split = defaultdict(list)
    for row in rows:
        by_split[row.split].append(row)
    del rows

    reference = build_reference(by_split["train"])
    save_reference(reference, MODEL_DIR)

    per_cutoff = defaultdict(list)
    for row in by_split["test"]:
        per_cutoff[row.cutoff].append(row)

    def per_cutoff_summary(transform=lambda rows: rows, columns=None):
        summary = {}
        for cutoff, cutoff_rows in sorted(per_cutoff.items()):
            entry = drift_report(reference, transform(cutoff_rows), columns)
            summary[cutoff.isoformat()] = {
                "max_psi": entry["max_psi"],
                "major": entry["major"],
            }
        return summary

    def fire_feed_down(rows):
        return [replace(row, **{column: 0 for column in FIRE_COUNTS}) for row in rows]

    report = {
        "reference_rows": reference["n_rows"],
        "validation_2023": drift_report(reference, by_split["validation"]),
        "test_2024": drift_report(reference, by_split["test"]),
        "test_2024_per_cutoff_weather": per_cutoff_summary(
            columns=tuple(WEATHER_FEATURES)
        ),
        "test_2024_per_cutoff_serving": per_cutoff_summary(
            columns=SERVING_DRIFT_FEATURES
        ),
        "simulated_fire_feed_down_per_cutoff": per_cutoff_summary(
            transform=fire_feed_down, columns=SERVING_DRIFT_FEATURES
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
