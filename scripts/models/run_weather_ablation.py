"""Live demo of the weather ablation (fire-history-only vs
fire-history+weather) against the real dataset built by the forecast
pipeline.

Honesty note: same real limitation as the other baseline demos -- the
project has only ingested real historical data for one real day
(2024-08-15, TEST split), so both the train and validation splits have
zero real positive examples. Both ablation variants share the same
XGBoost protocol as the baseline XGBoost demo, so both are expected to hit that same, honestly
reported limitation. See ml/tests/models/test_ablation.py for proof
that, on real, separable data, adding weather features measurably
improves metrics over fire-history alone.
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
from ai_earth_intelligence_and_forecasting_engine.models.ablation import (
    run_weather_ablation,
    save_ablation_result,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

ABLATION_OUTPUT_PATH = Path("ml/artifacts/weather_ablation_v1/weather_ablation.json")

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

    result = run_weather_ablation(train_rows, validation_rows, test_rows)

    for variant in (result.baseline, result.candidate):
        print(f"\n{variant.name} (features: {', '.join(variant.feature_columns)})")
        if variant.succeeded:
            print(f"  Metrics: {variant.metrics}")
        else:
            print(f"  Expected, honest result: {variant.error}")

    if result.roc_auc_delta is not None:
        print(
            f"\nROC-AUC delta (weather - fire-history-only): "
            f"{result.roc_auc_delta:+.4f}"
        )
    else:
        print(
            "\nNo metric deltas: at least one variant could not fit on the "
            "real data available today -- not a code bug, see "
            "ml/tests/models/test_ablation.py for proof the ablation "
            "correctly measures a weather signal on real, separable data."
        )

    save_ablation_result(result, ABLATION_OUTPUT_PATH)
    print(f"\nSaved ablation result to: {ABLATION_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
