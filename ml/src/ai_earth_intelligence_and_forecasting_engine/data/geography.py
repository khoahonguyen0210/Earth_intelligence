from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject
from rasterio.windows import from_bounds

DEM_TILE_BASE_URL = "https://copernicus-dem-30m.s3.amazonaws.com"
WORLDCOVER_TILE_BASE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
)

DEM_SOURCE = "Copernicus DEM GLO-30"
LANDCOVER_SOURCE = "ESA WorldCover 10m v200 2021"

GRID_RESOLUTION_DEG = 0.1

METERS_PER_DEGREE_LATITUDE = 111_320.0


@dataclass(frozen=True)
class GeographyConfig:
    grid_resolution_deg: float = GRID_RESOLUTION_DEG


@dataclass(frozen=True)
class GeographyCell:
    latitude: float
    longitude: float
    elevation_m: float
    slope_deg: float
    land_cover_class: int


def dem_tile_url(latitude: float, longitude: float) -> str:
    lat_floor = math.floor(latitude)
    lon_floor = math.floor(longitude)

    lat_hem = "N" if lat_floor >= 0 else "S"
    lon_hem = "E" if lon_floor >= 0 else "W"

    tile_name = (
        f"Copernicus_DSM_COG_10_{lat_hem}{abs(lat_floor):02d}_00_"
        f"{lon_hem}{abs(lon_floor):03d}_00_DEM"
    )

    return f"{DEM_TILE_BASE_URL}/{tile_name}/{tile_name}.tif"


def worldcover_tile_url(latitude: float, longitude: float) -> str:
    lat_floor = 3 * math.floor(latitude / 3)
    lon_floor = 3 * math.floor(longitude / 3)

    lat_hem = "N" if lat_floor >= 0 else "S"
    lon_hem = "E" if lon_floor >= 0 else "W"

    tile_name = (
        f"ESA_WorldCover_10m_2021_v200_"
        f"{lat_hem}{abs(lat_floor):02d}{lon_hem}{abs(lon_floor):03d}_Map"
    )

    return f"{WORLDCOVER_TILE_BASE_URL}/{tile_name}.tif"


def _fetch_window(
    source_url: str,
    bbox: tuple[float, float, float, float],
    output_path: Path,
) -> Path:
    west, south, east, north = bbox

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(f"/vsicurl/{source_url}") as src:
        window = from_bounds(west, south, east, north, transform=src.transform)
        data = src.read(1, window=window)
        transform = src.window_transform(window)

        profile = src.profile.copy()
        profile.update(height=data.shape[0], width=data.shape[1], transform=transform)

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data, 1)

    return output_path


def fetch_dem_sample(
    bbox: tuple[float, float, float, float],
    output_path: Path,
) -> Path:
    west, south, east, north = bbox
    url = dem_tile_url((south + north) / 2, (west + east) / 2)

    return _fetch_window(url, bbox, output_path)


def fetch_landcover_sample(
    bbox: tuple[float, float, float, float],
    output_path: Path,
) -> Path:
    west, south, east, north = bbox
    url = worldcover_tile_url((south + north) / 2, (west + east) / 2)

    return _fetch_window(url, bbox, output_path)


def compute_slope_degrees(
    elevation: np.ndarray,
    pixel_size_x_m: float,
    pixel_size_y_m: float,
) -> np.ndarray:
    dz_dy, dz_dx = np.gradient(elevation, pixel_size_y_m, pixel_size_x_m)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))

    return np.degrees(slope_rad)


def build_geography_grid(
    bbox: tuple[float, float, float, float],
    resolution_deg: float,
    dem_path: Path,
    landcover_path: Path,
) -> list[GeographyCell]:
    west, south, east, north = bbox

    width = round((east - west) / resolution_deg)
    height = round((north - south) / resolution_deg)

    dst_transform = from_origin(west, north, resolution_deg, resolution_deg)
    dst_crs = "EPSG:4326"

    with rasterio.open(dem_path) as dem_src:
        elevation = dem_src.read(1).astype("float64")

        mean_lat = (south + north) / 2
        pixel_size_x_m = (
            abs(dem_src.transform.a)
            * METERS_PER_DEGREE_LATITUDE
            * math.cos(math.radians(mean_lat))
        )
        pixel_size_y_m = abs(dem_src.transform.e) * METERS_PER_DEGREE_LATITUDE

        slope = compute_slope_degrees(elevation, pixel_size_x_m, pixel_size_y_m)

        dst_elevation = np.zeros((height, width), dtype="float64")
        reproject(
            source=elevation,
            destination=dst_elevation,
            src_transform=dem_src.transform,
            src_crs=dem_src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.average,
        )

        dst_slope = np.zeros((height, width), dtype="float64")
        reproject(
            source=slope,
            destination=dst_slope,
            src_transform=dem_src.transform,
            src_crs=dem_src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.average,
        )

    with rasterio.open(landcover_path) as lc_src:
        land_cover = lc_src.read(1)

        dst_land_cover = np.zeros((height, width), dtype=land_cover.dtype)
        reproject(
            source=land_cover,
            destination=dst_land_cover,
            src_transform=lc_src.transform,
            src_crs=lc_src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.mode,
        )

    records: list[GeographyCell] = []

    for row in range(height):
        for col in range(width):
            cell_west = west + col * resolution_deg
            cell_north = north - row * resolution_deg

            records.append(
                GeographyCell(
                    latitude=round(cell_north - resolution_deg / 2, 6),
                    longitude=round(cell_west + resolution_deg / 2, 6),
                    elevation_m=float(dst_elevation[row, col]),
                    slope_deg=float(dst_slope[row, col]),
                    land_cover_class=int(dst_land_cover[row, col]),
                )
            )

    return records


def save_geography_records(records: list[GeographyCell], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("latitude,longitude,elevation_m,slope_deg,land_cover_class\n")

        for record in records:
            handle.write(
                f"{record.latitude},{record.longitude},"
                f"{record.elevation_m},{record.slope_deg},"
                f"{record.land_cover_class}\n"
            )

    return output_path


def build_provenance(
    bbox: tuple[float, float, float, float],
    resolution_deg: float,
    dem_url: str,
    landcover_url: str,
    retrieved_at: datetime,
) -> dict[str, object]:
    return {
        "dem_source": DEM_SOURCE,
        "dem_url": dem_url,
        "landcover_source": LANDCOVER_SOURCE,
        "landcover_url": landcover_url,
        "bbox": list(bbox),
        "resolution_deg": resolution_deg,
        "retrieved_at": retrieved_at.isoformat(),
    }


def save_provenance(provenance: dict[str, object], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    return output_path
