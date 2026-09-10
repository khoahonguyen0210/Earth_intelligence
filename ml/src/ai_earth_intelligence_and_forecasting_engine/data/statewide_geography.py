"""Static geography (elevation, slope, land cover) for every California cell.

The original sample data covers one 0.4 x 0.4 degree box (16 grid
cells), so 9,959 of the 9,975 benchmark cells had no geography features
at all.
This builds the same features for the whole grid by walking 1-degree
tiles and running each one through the locked `build_geography_grid`
unchanged:

- DEM: Copernicus GLO-30 at full 30 m resolution (the tile's own pixels),
  exactly as the sample -- slope is computed at 30 m and then averaged
  into the 0.1-degree cell.
- Land cover: ESA WorldCover v200 read from the COG's 1/8 overview
  (~80 m) instead of 10 m. The cell value is the mode of ~19,000 such
  pixels; reading 10 m would mean ~1 GB per 3-degree tile for a
  majority class over an 11 km cell that the coarser read reproduces.
  docs/historical-dataset.md records this deviation.

Tiles with no DEM (open ocean) are skipped; their cells keep no
geography, which the feature step already treats as missing.
"""

from __future__ import annotations

import csv
import math
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.transform import Affine
from rasterio.windows import from_bounds

from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    GeographyCell,
    build_geography_grid,
    dem_tile_url,
    worldcover_tile_url,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
)

LANDCOVER_OVERVIEW_FACTOR = 8


def one_degree_tiles(
    bbox: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    """1-degree boxes covering `bbox`, clipped to it, west-to-east then
    south-to-north. Clipping keeps every 0.1-degree cell edge aligned with
    the benchmark grid (CALIFORNIA_BBOX edges are multiples of 0.5)."""
    west, south, east, north = bbox
    tiles = []
    for lat in range(math.floor(south), math.ceil(north)):
        for lon in range(math.floor(west), math.ceil(east)):
            tile = (max(lon, west), max(lat, south), min(lon + 1, east), min(lat + 1, north))
            if tile[2] > tile[0] and tile[3] > tile[1]:
                tiles.append(tile)
    return tiles


def _write_window(url: str, bbox, output_path: Path, decimation: int) -> bool:
    """Writes `bbox` of the COG at `url` to a local GeoTIFF, read at
    1/`decimation` resolution (GDAL serves it from the matching overview).
    False if there is no tile at `url`."""
    west, south, east, north = bbox
    try:
        src = rasterio.open(f"/vsicurl/{url}")
    except RasterioIOError:
        return False  # no tile here (e.g. open ocean)
    with src:
        window = from_bounds(west, south, east, north, transform=src.transform)
        height = max(1, round(window.height / decimation))
        width = max(1, round(window.width / decimation))
        data = src.read(1, window=window, out_shape=(height, width))
        transform = src.window_transform(window) * Affine.scale(
            window.width / width, window.height / height
        )
        profile = {
            "driver": "GTiff",
            "dtype": data.dtype,
            "count": 1,
            "height": height,
            "width": width,
            "crs": src.crs,
            "transform": transform,
            "compress": "deflate",
        }
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data, 1)
    return True


def build_tile(
    tile: tuple[float, float, float, float], resolution_deg: float = GRID_RESOLUTION_DEG
) -> list[GeographyCell]:
    west, south, east, north = tile
    center_lat, center_lon = (south + north) / 2, (west + east) / 2
    with tempfile.TemporaryDirectory() as tmp:
        dem_path = Path(tmp) / "dem.tif"
        landcover_path = Path(tmp) / "landcover.tif"
        if not _write_window(dem_tile_url(center_lat, center_lon), tile, dem_path, 1):
            return []
        if not _write_window(
            worldcover_tile_url(center_lat, center_lon),
            tile,
            landcover_path,
            LANDCOVER_OVERVIEW_FACTOR,
        ):
            return []
        return build_geography_grid(tile, resolution_deg, dem_path, landcover_path)


def build_statewide_geography(
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
    workers: int = 4,
    progress=None,
) -> list[GeographyCell]:
    tiles = one_degree_tiles(bbox)
    cells: list[GeographyCell] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for number, tile_cells in enumerate(
            pool.map(lambda tile: build_tile(tile, resolution_deg), tiles), start=1
        ):
            cells.extend(tile_cells)
            if progress:
                progress(number, len(tiles), len(tile_cells))
    return cells


def load_geography_records(path: Path) -> list[GeographyCell]:
    with path.open(encoding="utf-8") as handle:
        return [
            GeographyCell(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                elevation_m=float(row["elevation_m"]),
                slope_deg=float(row["slope_deg"]),
                land_cover_class=int(row["land_cover_class"]),
            )
            for row in csv.DictReader(handle)
        ]
