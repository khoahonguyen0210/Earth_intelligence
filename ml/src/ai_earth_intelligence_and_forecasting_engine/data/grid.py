from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

CALIFORNIA_BBOX: tuple[float, float, float, float] = (-124.5, 32.5, -114.0, 42.0)
GRID_RESOLUTION_DEG = 0.1
GRID_VERSION = "v1"


@dataclass(frozen=True)
class GridConfig:
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX
    resolution_deg: float = GRID_RESOLUTION_DEG
    version: str = GRID_VERSION


@dataclass(frozen=True)
class GridCell:
    tile_id: str
    lat_index: int
    lon_index: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    centroid_lon: float
    centroid_lat: float
    geometry: dict[str, Any]


def build_tile_id(lat_index: int, lon_index: int) -> str:
    return f"CA_{lat_index:04d}_{lon_index:04d}"


def bbox_polygon(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float
) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        ],
    }


def build_california_grid(
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> list[GridCell]:
    west, south, east, north = bbox

    width = round((east - west) / resolution_deg)
    height = round((north - south) / resolution_deg)

    cells: list[GridCell] = []

    for lat_index in range(height):
        min_lat = round(south + lat_index * resolution_deg, 6)
        max_lat = round(min_lat + resolution_deg, 6)

        for lon_index in range(width):
            min_lon = round(west + lon_index * resolution_deg, 6)
            max_lon = round(min_lon + resolution_deg, 6)

            cells.append(
                GridCell(
                    tile_id=build_tile_id(lat_index, lon_index),
                    lat_index=lat_index,
                    lon_index=lon_index,
                    min_lon=min_lon,
                    min_lat=min_lat,
                    max_lon=max_lon,
                    max_lat=max_lat,
                    centroid_lon=round((min_lon + max_lon) / 2, 6),
                    centroid_lat=round((min_lat + max_lat) / 2, 6),
                    geometry=bbox_polygon(min_lon, min_lat, max_lon, max_lat),
                )
            )

    return cells


def locate_cell(
    latitude: float,
    longitude: float,
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> GridCell | None:
    west, south, east, north = bbox

    if not (west <= longitude < east and south <= latitude < north):
        return None

    width = round((east - west) / resolution_deg)
    height = round((north - south) / resolution_deg)

    # A small epsilon guards against float division landing just under an
    # exact integer boundary (e.g. 104.99999999997 instead of 105).
    lon_index = min(
        int(math.floor((longitude - west) / resolution_deg + 1e-9)), width - 1
    )
    lat_index = min(
        int(math.floor((latitude - south) / resolution_deg + 1e-9)), height - 1
    )

    min_lon = round(west + lon_index * resolution_deg, 6)
    max_lon = round(min_lon + resolution_deg, 6)
    min_lat = round(south + lat_index * resolution_deg, 6)
    max_lat = round(min_lat + resolution_deg, 6)

    return GridCell(
        tile_id=build_tile_id(lat_index, lon_index),
        lat_index=lat_index,
        lon_index=lon_index,
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
        centroid_lon=round((min_lon + max_lon) / 2, 6),
        centroid_lat=round((min_lat + max_lat) / 2, 6),
        geometry=bbox_polygon(min_lon, min_lat, max_lon, max_lat),
    )


def locate_tile(
    latitude: float,
    longitude: float,
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> str | None:
    cell = locate_cell(latitude, longitude, bbox, resolution_deg)

    return cell.tile_id if cell else None


def is_valid_polygon(geometry: dict[str, Any]) -> bool:
    if geometry.get("type") != "Polygon":
        return False

    coordinates = geometry.get("coordinates")

    if not coordinates or len(coordinates) != 1:
        return False

    ring = coordinates[0]

    if len(ring) < 4 or ring[0] != ring[-1]:
        return False

    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]

    return max(lons) > min(lons) and max(lats) > min(lats)


def cell_to_feature(cell: GridCell) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": cell.tile_id,
        "geometry": cell.geometry,
        "properties": {
            "tile_id": cell.tile_id,
            "lat_index": cell.lat_index,
            "lon_index": cell.lon_index,
            "min_lon": cell.min_lon,
            "min_lat": cell.min_lat,
            "max_lon": cell.max_lon,
            "max_lat": cell.max_lat,
            "centroid_lon": cell.centroid_lon,
            "centroid_lat": cell.centroid_lat,
        },
    }


def cells_to_geojson(cells: list[GridCell]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [cell_to_feature(cell) for cell in cells],
    }


def save_grid_geojson(cells: list[GridCell], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cells_to_geojson(cells)), encoding="utf-8")

    return output_path


def build_grid_metadata(
    bbox: tuple[float, float, float, float],
    resolution_deg: float,
    version: str,
    cell_count: int,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "grid_version": version,
        "bbox": list(bbox),
        "resolution_deg": resolution_deg,
        "cell_count": cell_count,
        "boundary_rule": (
            "Cell (lat_index, lon_index) covers the half-open interval "
            "[west + lon_index*res, west + (lon_index+1)*res) in longitude and "
            "[south + lat_index*res, south + (lat_index+1)*res) in latitude. "
            "lat_index and lon_index start at 0 at the bbox south-west corner. "
            "The bbox east/north edges are the exclusive upper bound of the "
            "grid; no cell extends beyond them."
        ),
        "created_at": created_at.isoformat(),
    }


def save_grid_metadata(metadata: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return output_path
