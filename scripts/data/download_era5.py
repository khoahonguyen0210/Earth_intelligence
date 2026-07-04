from datetime import date
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    fetch_era5_sample,
    load_era5_config,
)


def main() -> None:
    config = load_era5_config()

    # Small bounded sample in California, matching the FIRMS sample bbox.
    bbox = (-124.5, 32.5, -114.0, 42.0)
    observed_date = date(2024, 8, 15)
    hour = "10:00"

    output_path = Path("data/raw/era5/era5_sample.nc")

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

    print(f"Saved ERA5-Land sample to: {result}")


if __name__ == "__main__":
    main()
