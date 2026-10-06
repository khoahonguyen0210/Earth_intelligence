from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    fetch_firms_sample,
    load_firms_config,
)
from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    build_provenance,
    save_provenance,
)


def main() -> None:
    config = load_firms_config()

    bbox = (-124.5, 32.5, -114.0, 42.0)
    observed_date = date(2024, 8, 15)

    output_path = Path("data/raw/firms/firms_sample.csv")
    provenance_output_path = Path("data/raw/firms/provenance.json")

    print("Product:", config.product)
    print("BBox:", bbox)
    print("Date:", observed_date)

    result = fetch_firms_sample(
        config=config,
        bbox=bbox,
        observed_date=observed_date,
        output_path=output_path,
    )

    period_start = datetime.combine(observed_date, time.min, tzinfo=timezone.utc)
    period_end = period_start + timedelta(days=1)

    provenance = build_provenance(
        source="NASA_FIRMS",
        product=config.product,
        dataset_version=f"{config.product}-standard-processing",
        period_start=period_start,
        period_end=period_end,
        raw_file_path=result,
        parameters={"bbox": list(bbox), "day_range": 1},
    )
    save_provenance(provenance, provenance_output_path)

    print(f"Saved FIRMS sample to: {result}")
    print(f"Saved provenance to: {provenance_output_path}")


if __name__ == "__main__":
    main()
