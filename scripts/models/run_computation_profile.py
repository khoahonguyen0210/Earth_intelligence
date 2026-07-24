"""Task 5.4: profile the real Task 3.7 pipeline -- data loading, feature
construction, training, inference, memory, and I/O -- against the real
sample data footprint.

Honesty note: data loading, feature construction, and I/O are measured
against 100% real data, same as every other Phase 4/5 demo. Training/
inference for climatology are also real. For logistic regression,
XGBoost, and calibrated XGBoost, the real train/validation splits still
have zero real positive examples (see every Phase 4 demo for why), so
those models cannot really fit; profile_model falls back to
synthetically-shaped (but realistically-sized) data purely to measure
wall-clock time and memory, never to report an accuracy number. Each
model's profile records used_synthetic_timing_data so this is never
silently conflated with a real training run.
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
from ai_earth_intelligence_and_forecasting_engine.models.profiling import (
    ComputationProfile,
    profile_all_models,
    profile_input_files,
    profile_stage,
    save_computation_profile,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

PROFILE_OUTPUT_PATH = Path(
    "ml/artifacts/computation_profile_v1/computation_profile.json"
)

TRAIN_DEMO_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
VALIDATION_DEMO_CUTOFF = datetime(2023, 8, 15, 10, 0, tzinfo=timezone.utc)
TEST_CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)


def _load_raw_data() -> tuple[list, list, list]:
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

    return observations, era5_records, (geography_cells, cells)


def main() -> None:
    input_files = profile_input_files(
        {
            "firms_sample_csv": RAW_FIRMS_PATH,
            "era5_sample_nc": RAW_ERA5_PATH,
            "dem_sample_tif": DEM_PATH,
            "landcover_sample_tif": LANDCOVER_PATH,
        }
    )

    (observations, era5_records, geography), data_loading_stage = profile_stage(
        "data_loading", _load_raw_data
    )
    geography_cells, cells = geography

    rows, feature_construction_stage = profile_stage(
        "feature_construction",
        lambda: build_dataset(
            observations,
            era5_records,
            geography_cells,
            cells,
            [TRAIN_DEMO_CUTOFF, VALIDATION_DEMO_CUTOFF, TEST_CUTOFF],
        ),
    )

    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    test_rows = [row for row in rows if row.split == "test"]

    model_profiles = profile_all_models(train_rows, validation_rows, test_rows)

    profile = ComputationProfile(
        input_files=input_files,
        data_loading=data_loading_stage,
        feature_construction=feature_construction_stage,
        row_counts={
            "train": len(train_rows),
            "validation": len(validation_rows),
            "test": len(test_rows),
        },
        models=model_profiles,
    )

    print("I/O (real input files):")
    for item in input_files:
        print(f"  {item.name}: {item.size_bytes / 1024:.1f} KB")

    print(
        f"\nData loading: {data_loading_stage.wall_time_seconds:.4f}s, "
        f"{data_loading_stage.peak_memory_mb:.2f} MB peak"
    )
    print(
        f"Feature construction: {feature_construction_stage.wall_time_seconds:.4f}s, "
        f"{feature_construction_stage.peak_memory_mb:.2f} MB peak "
        f"({len(rows)} rows produced)"
    )

    print(
        f"\n{'Model':<22}{'Synthetic':<11}{'Train (s)':<12}"
        f"{'Infer (s)':<12}{'Memory (MB)':<12}"
    )
    for item in model_profiles:
        train_time = (
            f"{item.training_time_seconds:.4f}"
            if item.training_time_seconds is not None
            else "n/a"
        )
        infer_time = (
            f"{item.inference_time_seconds:.4f}"
            if item.inference_time_seconds is not None
            else "n/a"
        )
        memory = (
            f"{item.peak_memory_mb:.2f}" if item.peak_memory_mb is not None else "n/a"
        )
        print(
            f"{item.model:<22}{str(item.used_synthetic_timing_data):<11}"
            f"{train_time:<12}{infer_time:<12}{memory:<12}"
        )
        if item.error:
            print(f"    -> {item.error}")

    save_computation_profile(profile, PROFILE_OUTPUT_PATH)
    print(f"\nSaved computation profile to: {PROFILE_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
