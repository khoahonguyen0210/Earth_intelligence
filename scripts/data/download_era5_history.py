import argparse
from datetime import datetime, timezone
from pathlib import Path

import cdsapi

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    build_area,
    load_era5_config,
)
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    era5_file_name,
    historical_cutoffs,
    required_era5_requests,
)
from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    build_provenance,
    save_provenance,
)

CALIFORNIA_BBOX = (-124.5, 32.5, -114.0, 42.0)
HISTORY_DIR = Path("data/raw/era5/history")

def season_cutoffs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    year = parser.parse_args().year
    return historical_cutoffs() if year is None else historical_cutoffs(year, year)


def main() -> None:
    config = load_era5_config()
    client = cdsapi.Client(url=config.url, key=config.key, quiet=True)
    requests = required_era5_requests(season_cutoffs())
    print(f"{len(requests)} ERA5-Land requests ({config.dataset})")

    for number, (year, month, days, hour) in enumerate(requests, start=1):
        output_path = HISTORY_DIR / era5_file_name(year, month)
        if output_path.exists():
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = output_path.with_suffix(".nc.part")
        client.retrieve(
            config.dataset,
            {
                "variable": list(config.variables),
                "year": f"{year:04d}",
                "month": f"{month:02d}",
                "day": [f"{day:02d}" for day in days],
                "time": hour,
                "area": build_area(CALIFORNIA_BBOX),
                "data_format": "netcdf",
                "download_format": "unarchived",
            },
            str(partial_path),
        )
        partial_path.replace(output_path)

        hour_value = int(hour.split(":")[0])
        provenance = build_provenance(
            source="ECMWF_CDS",
            product=config.dataset,
            dataset_version=config.dataset,
            period_start=datetime(year, month, days[0], hour_value, tzinfo=timezone.utc),
            period_end=datetime(year, month, days[-1], hour_value, tzinfo=timezone.utc),
            raw_file_path=output_path,
            parameters={
                "bbox": list(CALIFORNIA_BBOX),
                "variables": list(config.variables),
                "days": days,
                "hour": hour,
            },
        )
        save_provenance(provenance, output_path.with_suffix(".provenance.json"))
        print(f"[{number}/{len(requests)}] {output_path.name}: days {days} at {hour}")

    print("done")


if __name__ == "__main__":
    main()
