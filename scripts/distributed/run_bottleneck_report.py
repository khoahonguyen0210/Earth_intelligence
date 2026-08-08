import json
from dataclasses import asdict
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.distributed.bottleneck import (
    identify_bottleneck,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
    run_distributed_inference,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.scaling import (
    WORKER_COUNTS,
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

OUTPUT_PATH = Path("data/processed/distributed/bottleneck_report.json")


def main() -> None:
    workload = freeze_workload()
    context = prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )

    # Task 9.2's real one-worker run supplies the real per-tile compute
    # cost the "cpu" candidate is judged against.
    baseline = run_distributed_inference(workload, num_workers=1, context=context)

    report = identify_bottleneck(
        context,
        worker_counts=WORKER_COUNTS,
        real_compute_seconds=baseline.total_cpu_seconds,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    print("Task 9.4 bottleneck report:")
    print(f"  real_compute_seconds: {report.real_compute_seconds_for_full_workload:.4f}")
    print(f"  data_loading_seconds: {report.data_loading_seconds:.4f}")
    print(
        "  serialization_seconds: "
        f"{report.serialization_cost.pickle_seconds + report.serialization_cost.unpickle_seconds:.4f}"
        f" ({report.serialization_cost.payload_bytes} bytes per task)"
    )
    for overhead in report.spawn_overhead:
        print(f"  spawn_overhead[{overhead.num_workers}]: {overhead.wall_seconds:.4f}s")
    print(f"  DOMINANT FACTOR: {report.dominant_factor}")
    print(f"  {report.reasoning}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
