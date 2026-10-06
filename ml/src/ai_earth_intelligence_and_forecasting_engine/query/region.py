from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    bbox_polygon,
    locate_cell,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec

NAMED_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "california": CALIFORNIA_BBOX,
    "northern_california": (-124.5, 38.5, -119.0, 42.0),
    "southern_california": (-121.0, 32.5, -114.0, 35.5),
    "central_valley": (-122.5, 34.5, -118.5, 40.5),
    "bay_area": (-123.3, 36.9, -121.2, 38.9),
}


@dataclass(frozen=True)
class NormalizedRegion:
    bbox: tuple[float, float, float, float]
    geometry: dict[str, Any]
    source_kind: str
    label: str | None = None


def normalize_region(region: RegionSpec) -> NormalizedRegion:
    if region.kind == "bbox":
        return _normalize_bbox(region.value)

    if region.kind == "coordinates":
        return _normalize_coordinates(region.value)

    if region.kind == "named":
        return _normalize_named(region.value)

    raise ValueError(f"Unsupported region kind: {region.kind}")


def _normalize_bbox(value: Any) -> NormalizedRegion:
    if not (isinstance(value, tuple | list) and len(value) == 4):
        raise ValueError(f"bbox region value must be 4 floats, got: {value!r}")

    west, south, east, north = (float(component) for component in value)

    if west >= east or south >= north:
        raise ValueError(f"bbox region is degenerate or inverted: {value!r}")

    return NormalizedRegion(
        bbox=(west, south, east, north),
        geometry=bbox_polygon(west, south, east, north),
        source_kind="bbox",
    )


def _normalize_coordinates(value: Any) -> NormalizedRegion:
    if not (isinstance(value, tuple | list) and len(value) == 2):
        raise ValueError(
            f"coordinates region value must be (latitude, longitude), "
            f"got: {value!r}"
        )

    latitude, longitude = (float(component) for component in value)

    cell = locate_cell(latitude, longitude)

    if cell is None:
        raise ValueError(
            f"coordinates ({latitude}, {longitude}) fall outside the "
            "supported California grid"
        )

    return NormalizedRegion(
        bbox=(cell.min_lon, cell.min_lat, cell.max_lon, cell.max_lat),
        geometry=cell.geometry,
        source_kind="coordinates",
        label=cell.tile_id,
    )


def _normalize_named(value: Any) -> NormalizedRegion:
    if not isinstance(value, str):
        raise ValueError(f"named region value must be a string, got: {value!r}")

    key = value.strip().lower().replace(" ", "_")

    if key not in NAMED_REGIONS:
        raise ValueError(
            f"Unsupported named region: {value!r}. "
            f"Supported: {sorted(NAMED_REGIONS)}"
        )

    west, south, east, north = NAMED_REGIONS[key]

    return NormalizedRegion(
        bbox=(west, south, east, north),
        geometry=bbox_polygon(west, south, east, north),
        source_kind="named",
        label=key,
    )
