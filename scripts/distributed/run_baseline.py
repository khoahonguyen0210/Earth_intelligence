import json
from dataclasses import asdict
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
    run_distributed_inference,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    freeze_workload,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

OUTPUT_PATH = Path("data/processed/distributed/one_worker_baseline.json")


def main() -> None:
    workload = freeze_workload()
    context = prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )
    result = run_distributed_inference(workload, num_workers=1, context=context)

    record = {
        "workload": asdict(workload) | {"workload_size": workload.workload_size},
        "data_loading": asdict(context.data_loading),
        "result": asdict(result),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"One-worker baseline ({result.workload_size} tiles):")
    print(f"  wall_seconds:        {result.wall_seconds:.3f}")
    print(f"  throughput (tiles/s): {result.throughput_tiles_per_second:.3f}")
    print(f"  total_cpu_seconds:   {result.total_cpu_seconds:.3f}")
    print(f"  peak_memory_mb:      {result.peak_memory_mb:.3f}")
    print(f"  data_loading:        {context.data_loading}")
    print(f"  used_synthetic_model_fallback: {result.used_synthetic_model_fallback}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
