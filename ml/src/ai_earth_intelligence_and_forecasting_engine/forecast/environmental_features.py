from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    ERA5Record,
    relative_humidity_percent,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridCell,
    locate_tile,
)

FEATURE_DATASET_VERSION = "v1"


@dataclass(frozen=True)
class EnvironmentalFeatures:
    tile_id: str
    cutoff: datetime
    temperature_2m: float | None
    total_precipitation: float | None
    u_wind_10m: float | None
    v_wind_10m: float | None
    relative_humidity: float | None
    era5_valid_time: str | None


def compute_environmental_features(
    era5_records: list[ERA5Record],
    cells: list[GridCell],
    cutoffs: list[datetime],
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> list[EnvironmentalFeatures]:
    """`bbox`/`resolution_deg` must match whatever `cells` was built with,
    same as `construct_labels` and `compute_fire_history_features`.

    For each (tile, cutoff), uses the most recent ERA5-Land record in that
    tile with `valid_time <= cutoff` -- "only cutoff-compatible
    observations may be used" -- never a record whose valid_time is after
    the cutoff.
    """
    records_by_tile: dict[str, list[ERA5Record]] = {}

    for record in era5_records:
        tile_id = locate_tile(record.latitude, record.longitude, bbox, resolution_deg)

        if tile_id is None:
            continue

        records_by_tile.setdefault(tile_id, []).append(record)

    for tile_records in records_by_tile.values():
        tile_records.sort(key=lambda record: record.valid_time)

    results: list[EnvironmentalFeatures] = []

    for cutoff in cutoffs:
        for cell in cells:
            tile_records = records_by_tile.get(cell.tile_id, [])

            # tile_records is sorted ascending by valid_time; the last
            # eligible, non-NaN entry is the most recent usable one. ERA5-
            # Land masks ocean cells as NaN (Task 1.5), which is not
            # "missing because not yet available" -- treat it the same as
            # no record at all rather than passing NaN through.
            latest = None
            for record in tile_records:
                if record.valid_time > cutoff:
                    break
                if math.isnan(record.temperature_2m):
                    continue
                latest = record

            if latest is None:
                results.append(
                    EnvironmentalFeatures(
                        tile_id=cell.tile_id,
                        cutoff=cutoff,
                        temperature_2m=None,
                        total_precipitation=None,
                        u_wind_10m=None,
                        v_wind_10m=None,
                        relative_humidity=None,
                        era5_valid_time=None,
                    )
                )
                continue

            results.append(
                EnvironmentalFeatures(
                    tile_id=cell.tile_id,
                    cutoff=cutoff,
                    temperature_2m=latest.temperature_2m,
                    total_precipitation=latest.total_precipitation,
                    u_wind_10m=latest.u_wind_10m,
                    v_wind_10m=latest.v_wind_10m,
                    relative_humidity=relative_humidity_percent(
                        latest.temperature_2m, latest.dewpoint_2m
                    ),
                    era5_valid_time=latest.valid_time.isoformat(),
                )
            )

    return results


def save_environmental_features(
    records: list[EnvironmentalFeatures], output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(
            "tile_id,cutoff,temperature_2m,total_precipitation,"
            "u_wind_10m,v_wind_10m,relative_humidity,era5_valid_time\n"
        )

        for record in records:
            handle.write(
                f"{record.tile_id},{record.cutoff.isoformat()},"
                f"{record.temperature_2m},{record.total_precipitation},"
                f"{record.u_wind_10m},{record.v_wind_10m},"
                f"{record.relative_humidity},{record.era5_valid_time}\n"
            )

    return output_path
