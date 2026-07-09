import json
import sys
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    run_analysis,
)

# Run from the project root; matches every other scripts/data/*.py adapter.
RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        response = run_analysis(payload, RAW_FIRMS_PATH)
    except Exception as error:
        json.dump({"error": str(error)}, sys.stdout)
        sys.exit(1)

    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
