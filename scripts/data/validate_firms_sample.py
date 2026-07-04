from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.validation import (
    save_validation_report,
    validate_observations,
)


def main() -> None:
    config = load_firms_config()

    input_path = Path("data/raw/firms/firms_sample.csv")
    output_path = Path("data/processed/validation/validation_report.json")

    csv_text = input_path.read_text(encoding="utf-8")
    records = parse_firms_records(csv_text)

    ingested_at = datetime.now(timezone.utc)
    observations = [
        normalize_firms_record(
            record=record,
            product=config.product,
            source_record_id=str(index),
            ingested_at=ingested_at,
        )
        for index, record in enumerate(records)
    ]

    report = validate_observations(observations)
    save_validation_report(report, output_path)

    print("Total records:", report.total_records)
    print("Valid records:", report.valid_records)
    print("Invalid records:", report.invalid_records)
    print("Issues by category:", report.issues_by_category)
    print(f"Saved validation report to: {output_path}")


if __name__ == "__main__":
    main()
