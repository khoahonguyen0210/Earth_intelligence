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
from ai_earth_intelligence_and_forecasting_engine.models.climatology import (
    MODEL_VERSION,
    evaluate_climatology,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    metrics_to_dict,
    save_metrics,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

ARTIFACT_DIR = Path("ml/artifacts/climatology_v1")

TRAIN_DEMO_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
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
        [TRAIN_DEMO_CUTOFF, TEST_CUTOFF],
    )

    train_rows = [row for row in rows if row.split == "train"]
    test_rows = [row for row in rows if row.split == "test"]

    print(f"Train rows: {len(train_rows)}, test rows: {len(test_rows)}")

    model, predictions, metrics = evaluate_climatology(train_rows, test_rows)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    save_metrics(metrics, ARTIFACT_DIR / "metrics.json")

    (ARTIFACT_DIR / "config.json").write_text(
        f'{{"model": "climatology", "model_version": "{MODEL_VERSION}"}}',
        encoding="utf-8",
    )

    predictions_path = ARTIFACT_DIR / "predictions.csv"
    with predictions_path.open("w", encoding="utf-8") as handle:
        handle.write("tile_id,cutoff,target,predicted_probability\n")
        for row, prediction in zip(test_rows, predictions):
            handle.write(
                f"{row.tile_id},{row.cutoff.isoformat()},"
                f"{row.target},{prediction}\n"
            )

    print(f"\nGlobal training rate: {model.global_rate}")
    print(f"Tiles with a non-zero training rate: "
          f"{sum(1 for rate in model.tile_rates.values() if rate > 0)}")
    print(f"Metrics: {metrics_to_dict(metrics)}")
    print(f"\nSaved artifacts to: {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
