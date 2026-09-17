import json
from dataclasses import asdict
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.scaling import (
    WORKER_COUNTS,
    run_scaling_benchmark,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    freeze_workload,
)

# Same real sample-data paths every other scripts/query/*.py real-caller
# already uses (scripts/query/run_forecast_cli.py).
RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

OUTPUT_PATH = Path("data/processed/distributed/scaling_benchmark.json")


def main() -> None:
    workload = freeze_workload()
    context = prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )

    points = run_scaling_benchmark(workload, context, worker_counts=WORKER_COUNTS)

    record = {
        "workload": asdict(workload) | {"workload_size": workload.workload_size},
        "data_loading": asdict(context.data_loading),
        "used_synthetic_model_fallback": context.used_synthetic_model_fallback,
        "points": [
            asdict(point.result) | {"speedup": point.speedup, "efficiency": point.efficiency}
            for point in points
        ],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"Scaling benchmark ({workload.workload_size} tiles):")
    print(f"{'workers':>8} {'wall_s':>10} {'speedup':>10} {'efficiency':>12}")
    for point in points:
        print(
            f"{point.result.requested_workers:>8} "
            f"{point.result.wall_seconds:>10.3f} "
            f"{point.speedup:>10.3f} "
            f"{point.efficiency:>12.3f}"
        )
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
