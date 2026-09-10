import json
from dataclasses import asdict
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.distributed.fault_tolerance import (
    run_with_fault_tolerance,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
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

OUTPUT_PATH = Path("data/processed/distributed/fault_injection_report.json")

# 4 workers, not 8: an 8-worker cold-start alone measured at ~25s; this
# test needs a timeout comfortably larger than one worker's real
# replacement cold-start, without the whole run taking minutes.
NUM_WORKERS = 4
TASK_TIMEOUT_SECONDS = 30
MAX_RETRIES = 2
CRASH_CHUNK_INDEX = 0


def main() -> None:
    workload = freeze_workload()
    context = prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )

    result = run_with_fault_tolerance(
        workload,
        num_workers=NUM_WORKERS,
        context=context,
        task_timeout_seconds=TASK_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
        inject_crash_in_chunk=CRASH_CHUNK_INDEX,
    )

    record = {
        "workload_size": workload.workload_size,
        "num_workers": NUM_WORKERS,
        "task_timeout_seconds": TASK_TIMEOUT_SECONDS,
        "max_retries": MAX_RETRIES,
        "crash_chunk_index": CRASH_CHUNK_INDEX,
        "result": asdict(result),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"Task 9.5 fault-injection test ({workload.workload_size} tiles, {NUM_WORKERS} workers):")
    print(f"  any_failure_detected:          {result.any_failure_detected}")
    print(f"  all_chunks_eventually_succeeded: {result.all_chunks_eventually_succeeded}")
    print(f"  total_tiles_recovered:         {result.total_tiles}")
    print(f"  total_recovery_seconds:        {result.total_recovery_seconds:.3f}")
    for outcome in result.chunk_outcomes:
        print(
            f"    chunk {outcome.chunk_index}: attempts={outcome.attempts} "
            f"failure_detected={outcome.failure_detected} "
            f"result={'OK' if outcome.result else 'LOST'} "
            f"recovery_seconds={outcome.recovery_seconds}"
        )
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
