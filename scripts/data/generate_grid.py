from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GridConfig,
    build_california_grid,
    build_grid_metadata,
    save_grid_geojson,
    save_grid_metadata,
)


def main() -> None:
    config = GridConfig()

    cells = build_california_grid(bbox=config.bbox, resolution_deg=config.resolution_deg)

    grid_output_path = Path(
        f"data/processed/grid/california_grid_{config.version}.geojson"
    )
    metadata_output_path = Path("data/processed/grid/metadata.json")

    save_grid_geojson(cells, grid_output_path)

    metadata = build_grid_metadata(
        bbox=config.bbox,
        resolution_deg=config.resolution_deg,
        version=config.version,
        cell_count=len(cells),
        created_at=datetime.now(timezone.utc),
    )
    save_grid_metadata(metadata, metadata_output_path)

    print("Grid version:", config.version)
    print("BBox:", config.bbox)
    print("Resolution (deg):", config.resolution_deg)
    print("Cell count:", len(cells))
    print(f"Saved grid to: {grid_output_path}")
    print(f"Saved metadata to: {metadata_output_path}")


if __name__ == "__main__":
    main()
