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
from ai_earth_intelligence_and_forecasting_engine.models.benchmark import (
    run_baseline_benchmark,
    save_benchmark_comparison,
    save_benchmark_table,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

BENCHMARK_OUTPUT_DIR = Path("ml/artifacts/final_baseline_benchmark_v1")

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

    benchmark_rows = run_baseline_benchmark(train_rows, validation_rows, test_rows)

    save_benchmark_comparison(
        benchmark_rows, BENCHMARK_OUTPUT_DIR / "comparison.json"
    )
    save_benchmark_table(benchmark_rows, BENCHMARK_OUTPUT_DIR / "comparison.csv")

    print(f"{'Model':<22}{'Succeeded':<11}{'PR-AUC':<10}{'ROC-AUC':<10}{'Brier':<10}")
    for row in benchmark_rows:
        pr_auc = f"{row.pr_auc:.4f}" if row.pr_auc is not None else "n/a"
        roc_auc = f"{row.roc_auc:.4f}" if row.roc_auc is not None else "n/a"
        brier = f"{row.brier_score:.4f}" if row.brier_score is not None else "n/a"
        print(
            f"{row.model:<22}{str(row.succeeded):<11}{pr_auc:<10}{roc_auc:<10}{brier:<10}"
        )
        if row.error:
            print(f"    -> {row.error}")

    print(f"\nSaved benchmark comparison to: {BENCHMARK_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
