import argparse
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.kernels.bench import (
    Size,
    random_source,
    run,
    saved_source,
)

SIZES = [
    Size("one_global_field", 1),
    Size("lead_times_3_days", 12),
    Size("ensemble_16", 16),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ml/artifacts/gpu_perf"))
    parser.add_argument("--era5", type=Path)
    arguments = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if arguments.era5:
        source, name = saved_source(arguments.era5), "era5"
        run_id = f"{run_id}_era5"
    else:
        source, name = random_source, "random"
    measurements = run(SIZES, arguments.output / run_id, source, name)
    for item in measurements:
        print(
            f"{item.size:20} {item.implementation:14} {item.status:14} "
            f"{item.median_ms:9.3f} ms {item.percent_of_peak:6.1f}% "
            f"{item.percent_of_peak_sectors:6.1f}% ok={item.within_tolerance}"
        )


if __name__ == "__main__":
    main()
