import argparse
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import load_firms_config
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    fetch_firms_span,
    firms_spans,
    historical_cutoffs,
    required_firms_days,
)
from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    build_provenance,
    save_provenance,
)

CALIFORNIA_BBOX = (-124.5, 32.5, -114.0, 42.0)
HISTORY_DIR = Path("data/raw/firms/history")
PAUSE_SECONDS = 1.0

def season_cutoffs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int)
    year = parser.parse_args().year
    return historical_cutoffs() if year is None else historical_cutoffs(year, year)


def main() -> None:
    config = load_firms_config()
    spans = firms_spans(required_firms_days(season_cutoffs()))
    print(f"{len(spans)} FIRMS spans ({config.product}, bbox {CALIFORNIA_BBOX})")

    for number, span in enumerate(spans, start=1):
        output_path = HISTORY_DIR / span.file_name
        if output_path.exists():
            continue

        fetch_firms_span(config, CALIFORNIA_BBOX, span, output_path)

        period_start = datetime.combine(span.start, dtime.min, tzinfo=timezone.utc)
        provenance = build_provenance(
            source="NASA_FIRMS",
            product=config.product,
            dataset_version=f"{config.product}-standard-processing",
            period_start=period_start,
            period_end=period_start + timedelta(days=span.day_range),
            raw_file_path=output_path,
            parameters={"bbox": list(CALIFORNIA_BBOX), "day_range": span.day_range},
        )
        save_provenance(provenance, output_path.with_suffix(".provenance.json"))

        rows = output_path.read_text("utf-8").count("\n") - 1
        print(f"[{number}/{len(spans)}] {span.file_name}: {rows} detections")
        time.sleep(PAUSE_SECONDS)

    print("done")


if __name__ == "__main__":
    main()
