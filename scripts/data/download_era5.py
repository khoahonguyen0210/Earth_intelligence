from datetime import date, datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    fetch_era5_sample,
    load_era5_config,
)
from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    build_provenance,
    save_provenance,
)


def main() -> None:
    config = load_era5_config()

    bbox = (-124.5, 32.5, -114.0, 42.0)
    observed_date = date(2024, 8, 15)
    hour = "10:00"

    output_path = Path("data/raw/era5/era5_sample.nc")
    provenance_output_path = Path("data/raw/era5/provenance.json")

    print("Dataset:", config.dataset)
    print("Variables:", config.variables)
    print("BBox:", bbox)
    print("Date:", observed_date)
    print("Hour:", hour)

    result = fetch_era5_sample(
        config=config,
        bbox=bbox,
        observed_date=observed_date,
        hour=hour,
        output_path=output_path,
    )

    period_start = datetime(
        observed_date.year,
        observed_date.month,
        observed_date.day,
        int(hour.split(":")[0]),
        int(hour.split(":")[1]),
        tzinfo=timezone.utc,
    )

    provenance = build_provenance(
        source="ECMWF_CDS",
        product=config.dataset,
        dataset_version=config.dataset,
        period_start=period_start,
        period_end=period_start,
        raw_file_path=result,
        parameters={
            "bbox": list(bbox),
            "variables": list(config.variables),
            "hour": hour,
        },
    )
    save_provenance(provenance, provenance_output_path)

    print(f"Saved ERA5-Land sample to: {result}")
    print(f"Saved provenance to: {provenance_output_path}")


if __name__ == "__main__":
    main()
