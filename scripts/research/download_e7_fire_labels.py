import time
from datetime import timedelta
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import load_firms_config
from ai_earth_intelligence_and_forecasting_engine.data.grid import CALIFORNIA_BBOX
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    fetch_firms_span,
    firms_covered_days,
    firms_spans,
    historical_cutoffs,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    SPLIT_YEARS,
)

HISTORY_DIR = Path("data/raw/firms/history")
EXTRA_DIR = Path("data/raw/firms/e7_labels")
PAUSE_SECONDS = 1.0


def needed_days():
    years = sorted(year for group in SPLIT_YEARS.values() for year in group)
    days = set()
    for year in years:
        for cutoff in historical_cutoffs(year, year):
            for offset in range(LEAD_DAYS[-1] + 1):
                days.add((cutoff + timedelta(days=offset)).date())
    return days


def main() -> None:
    covered = firms_covered_days(HISTORY_DIR) | firms_covered_days(EXTRA_DIR)
    missing = sorted(needed_days() - covered)
    spans = firms_spans(missing)
    print(f"{len(missing)} days missing, {len(spans)} FIRMS requests")
    if not spans:
        return

    config = load_firms_config()
    for span in spans:
        output_path = EXTRA_DIR / span.file_name
        fetch_firms_span(config, CALIFORNIA_BBOX, span, output_path)
        rows = output_path.read_text("utf-8").count("\n") - 1
        print(f"{span.file_name}: {rows} detections")
        time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    main()
