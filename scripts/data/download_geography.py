from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    GeographyConfig,
    build_geography_grid,
    build_provenance,
    dem_tile_url,
    fetch_dem_sample,
    fetch_landcover_sample,
    save_geography_records,
    save_provenance,
    worldcover_tile_url,
)


def main() -> None:
    config = GeographyConfig()

    # Small bounded sample in the Sierra Nevada foothills: real elevation
    # relief for a meaningful slope check, fully inside one DEM tile and
    # one WorldCover tile.
    bbox = (-119.8, 37.2, -119.4, 37.6)

    dem_output_path = Path("data/raw/geography/dem_sample.tif")
    landcover_output_path = Path("data/raw/geography/landcover_sample.tif")
    grid_output_path = Path("data/processed/geography/geography_sample.csv")
    provenance_output_path = Path("data/processed/geography/provenance.json")

    centroid_lat = (bbox[1] + bbox[3]) / 2
    centroid_lon = (bbox[0] + bbox[2]) / 2
    dem_url = dem_tile_url(centroid_lat, centroid_lon)
    landcover_url = worldcover_tile_url(centroid_lat, centroid_lon)

    print("DEM source:", dem_url)
    print("Land-cover source:", landcover_url)
    print("BBox:", bbox)
    print("Resolution (deg):", config.grid_resolution_deg)

    fetch_dem_sample(bbox=bbox, output_path=dem_output_path)
    fetch_landcover_sample(bbox=bbox, output_path=landcover_output_path)

    records = build_geography_grid(
        bbox=bbox,
        resolution_deg=config.grid_resolution_deg,
        dem_path=dem_output_path,
        landcover_path=landcover_output_path,
    )

    save_geography_records(records, grid_output_path)

    provenance = build_provenance(
        bbox=bbox,
        resolution_deg=config.grid_resolution_deg,
        dem_url=dem_url,
        landcover_url=landcover_url,
        retrieved_at=datetime.now(timezone.utc),
    )
    save_provenance(provenance, provenance_output_path)

    print(f"Grid cells: {len(records)}")
    print(f"Saved geography grid to: {grid_output_path}")
    print(f"Saved provenance to: {provenance_output_path}")


if __name__ == "__main__":
    main()
