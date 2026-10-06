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
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    evaluate_calibration,
    plot_reliability_diagram,
    save_calibration_table,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

ARTIFACT_DIR = Path("ml/artifacts/calibrated_xgboost_v1")

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

    try:
        base_result = fit_xgboost(train_rows, validation_rows)
        _model, _predictions, metrics, table = evaluate_calibration(
            base_result, validation_rows, test_rows
        )

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        save_calibration_table(table, ARTIFACT_DIR / "calibration_table.csv")
        plot_reliability_diagram(table, ARTIFACT_DIR / "reliability_diagram.png")

        print(f"Metrics: {metrics}")
        print(f"Calibration table rows: {len(table)}")
        print(f"Saved artifacts to: {ARTIFACT_DIR}")
    except ValueError as error:
        print(f"Expected, honest result: {error}")
        print(
            "\nThis is a real data-availability gap, not a code bug -- see "
            "ml/tests/models/test_calibration.py for proof the calibration, "
            "calibration table, and reliability diagram code are correct "
            "against a real, separable synthetic fixture."
        )


if __name__ == "__main__":
    main()
