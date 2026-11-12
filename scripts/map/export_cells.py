from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.data.statewide_geography import (
    load_geography_records,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.daily_map import (
    CellGeography,
    save_cell_geography,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.geography_features import (
    compute_geography_features,
)

GEOGRAPHY_PATH = Path("data/raw/geography/california_geography.csv")
OUTPUT_PATH = Path("map/cells.csv")


def main() -> None:
    records = compute_geography_features(
        load_geography_records(GEOGRAPHY_PATH), build_california_grid()
    )
    geography = {
        record.tile_id: CellGeography(
            elevation_m=record.elevation_m,
            slope_deg=record.slope_deg,
            land_cover_class=record.land_cover_class,
        )
        for record in records
        if record.elevation_m is not None
        and record.slope_deg is not None
        and record.land_cover_class is not None
    }
    save_cell_geography(geography, OUTPUT_PATH)
    print(f"{len(geography)} cells written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
