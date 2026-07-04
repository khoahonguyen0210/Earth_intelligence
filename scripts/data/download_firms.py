from datetime import date
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    fetch_firms_sample,
    load_firms_config,
)


def main() -> None:
    config = load_firms_config()

    # Small bounded sample in California.
    bbox = (-124.5, 32.5, -114.0, 42.0)

    output_path = Path("data/raw/firms/firms_sample.csv")

    print("Product:", config.product)
    print("BBox:", bbox)
    print("Date:", date(2024, 8, 15))

    result = fetch_firms_sample(
        config=config,
        bbox=bbox,
        observed_date=date(2024, 8, 15),
        output_path=output_path,
    )

    print(f"Saved FIRMS sample to: {result}")


if __name__ == "__main__":
    main()