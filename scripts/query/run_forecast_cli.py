import json
import sys
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.query.run_forecast import (
    run_forecast,
)

FIRMS_HISTORY_DIR = Path("data/raw/firms/history")
ERA5_HISTORY_DIR = Path("data/raw/era5/history")
LIVE_DIR = Path("data/raw/live")
GEOGRAPHY_PATH =Path("data/raw/geography/california_geography.csv")
MODEL_DIR = Path("ml/artifacts/production_model_v1")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        response = run_forecast(
            payload,
            FIRMS_HISTORY_DIR,
            ERA5_HISTORY_DIR,
            GEOGRAPHY_PATH,
            MODEL_DIR,
            LIVE_DIR,
        )
    except Exception as error:
        json.dump({"error": str(error)}, sys.stdout)
        sys.exit(1)

    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
