import json
import sys
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.query.run_forecast import (
    run_forecast,
)

# Run from the project root; matches every other scripts/data/*.py adapter
# and scripts/query/run_analysis_cli.py's own sample-data paths.
RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        response = run_forecast(
            payload, RAW_FIRMS_PATH, RAW_ERA5_PATH, GEOGRAPHY_BBOX, DEM_PATH, LANDCOVER_PATH
        )
    except Exception as error:
        json.dump({"error": str(error)}, sys.stdout)
        sys.exit(1)

    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
