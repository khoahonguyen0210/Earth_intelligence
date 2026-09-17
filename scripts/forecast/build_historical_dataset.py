"""Build the real historical benchmark dataset.

Inputs (all real, all downloaded by scripts/data/*_history.py and
build_statewide_geography.py):
  data/raw/firms/history/          FIRMS VIIRS SNPP SP, fire seasons 2019-2024
  data/raw/era5/history/           ERA5-Land at every cutoff hour
  data/raw/geography/california_geography.csv

Outputs:
  data/processed/historical_dataset_v1.csv        one row per (cell, cutoff)
  data/processed/historical_dataset_v1.manifest.json

    python scripts/forecast/build_historical_dataset.py
"""

import json
import time
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    LOOKBACK_HOURS,
    historical_cutoffs,
    load_firms_history,
)
from ai_earth_intelligence_and_forecasting_engine.data.statewide_geography import (
    load_geography_records,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DATASET_HEADER,
    FEATURE_COLUMNS,
    build_dataset_manifest,
    manifest_to_dict,
    write_dataset_rows,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.historical_dataset import (
    ERA5History,
    ObservationIndex,
    iter_historical_rows,
)

FIRMS_DIR = Path("data/raw/firms/history")
ERA5_DIR = Path("data/raw/era5/history")
GEOGRAPHY_PATH = Path("data/raw/geography/california_geography.csv")
OUTPUT_PATH = Path("data/processed/historical_dataset_v1.csv")


class ManifestAccumulator:
    """Streams the counts build_dataset_manifest needs plus per-split
    missing-feature counts, without holding every row in memory."""

    def __init__(self):
        self.rows = 0
        self.by_split: dict[str, dict[str, int]] = {}

    def add(self, rows) -> None:
        for row in rows:
            self.rows += 1
            split = self.by_split.setdefault(
                row.split, {"rows": 0, "positives": 0, **{c: 0 for c in FEATURE_COLUMNS}}
            )
            split["rows"] += 1
            split["positives"] += row.target
            for column in FEATURE_COLUMNS:
                if getattr(row, column) is None:
                    split[column] += 1

    def summary(self) -> dict:
        return {
            split: {
                "rows": counts["rows"],
                "positives": counts["positives"],
                "positive_rate": counts["positives"] / counts["rows"],
                "missing_rate": {
                    column: counts[column] / counts["rows"] for column in FEATURE_COLUMNS
                },
            }
            for split, counts in sorted(self.by_split.items())
        }


def main() -> None:
    started = time.perf_counter()
    cutoffs = historical_cutoffs()
    cells = build_california_grid()
    geography = load_geography_records(GEOGRAPHY_PATH)

    window_start = cutoffs[0] - timedelta(hours=LOOKBACK_HOURS)
    window_end = cutoffs[-1] + timedelta(days=1)
    observations = ObservationIndex(load_firms_history(FIRMS_DIR, window_start, window_end))
    print(f"{len(observations)} FIRMS observations, {len(cells)} cells, "
          f"{len(cutoffs)} cutoffs, {len(geography)} geography cells", flush=True)

    era5 = ERA5History(ERA5_DIR)
    manifest = ManifestAccumulator()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        handle.write(DATASET_HEADER + "\n")
        for number, rows in enumerate(
            iter_historical_rows(observations, era5.for_cutoff, geography, cells, cutoffs),
            start=1,
        ):
            write_dataset_rows(handle, rows)
            manifest.add(rows)
            positives = sum(row.target for row in rows)
            print(f"[{number}/{len(cutoffs)}] {rows[0].cutoff.isoformat()} "
                  f"{rows[0].split}: {positives} positive cells", flush=True)

    base = manifest_to_dict(build_dataset_manifest([]))
    base.update(
        {
            "row_counts": {
                **{split: s["rows"] for split, s in manifest.summary().items()},
                "total": manifest.rows,
            },
            "positive_rates": {
                split: s["positive_rate"] for split, s in manifest.summary().items()
            },
            "splits": manifest.summary(),
            "cutoff_rule": "10:00 UTC every 7 days from June 1 through October, 2019-2024",
            "cutoffs": len(cutoffs),
            "cells": len(cells),
            "firms_observations_loaded": len(observations),
            "build_seconds": round(time.perf_counter() - started, 1),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "row_fields": [field.name for field in fields(type(rows[0]))],
        }
    )
    OUTPUT_PATH.with_suffix(".manifest.json").write_text(
        json.dumps(base, indent=2), encoding="utf-8"
    )
    print(json.dumps(base["splits"], indent=2))


if __name__ == "__main__":
    main()
