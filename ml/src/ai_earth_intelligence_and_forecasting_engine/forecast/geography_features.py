from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.geography import GeographyCell
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridCell,
    locate_tile,
)

FEATURE_DATASET_VERSION = "v1"


@dataclass(frozen=True)
class GeographyFeatures:
    tile_id: str
    elevation_m: float | None
    slope_deg: float | None
    land_cover_class: int | None


def compute_geography_features(
    geography_cells: list[GeographyCell],
    cells: list[GridCell],
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> list[GeographyFeatures]:
    values_by_tile: dict[str, GeographyCell] = {}

    for geo_cell in geography_cells:
        tile_id = locate_tile(
            geo_cell.latitude, geo_cell.longitude, bbox, resolution_deg
        )

        if tile_id is None:
            continue

        if math.isnan(geo_cell.elevation_m) or math.isnan(geo_cell.slope_deg):
            continue

        values_by_tile[tile_id] = geo_cell

    records: list[GeographyFeatures] = []

    for cell in cells:
        matched_cell = values_by_tile.get(cell.tile_id)

        if matched_cell is None:
            records.append(
                GeographyFeatures(
                    tile_id=cell.tile_id,
                    elevation_m=None,
                    slope_deg=None,
                    land_cover_class=None,
                )
            )
            continue

        records.append(
            GeographyFeatures(
                tile_id=cell.tile_id,
                elevation_m=matched_cell.elevation_m,
                slope_deg=matched_cell.slope_deg,
                land_cover_class=matched_cell.land_cover_class,
            )
        )

    return records


def save_geography_features(
    records: list[GeographyFeatures], output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("tile_id,elevation_m,slope_deg,land_cover_class\n")

        for record in records:
            handle.write(
                f"{record.tile_id},{record.elevation_m},"
                f"{record.slope_deg},{record.land_cover_class}\n"
            )

    return output_path
