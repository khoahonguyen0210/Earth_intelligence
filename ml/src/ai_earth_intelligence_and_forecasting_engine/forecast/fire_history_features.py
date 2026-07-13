from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridCell,
    locate_tile,
    neighbor_tile_ids,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast.labels import (
    is_qualifying_observation,
)

FEATURE_DATASET_VERSION = "v1"

# name -> lookback window length in hours. Every window is
# (cutoff - hours, cutoff] -- closed at the cutoff, per "every window ends
# at or before the cutoff" (the complement of Task 3.2's forward label
# window, which excludes the cutoff itself).
FIRE_HISTORY_WINDOWS_HOURS: dict[str, int] = {
    "previous_24h_count": 24,
    "previous_72h_count": 72,
    "previous_7d_count": 24 * 7,
    "previous_30d_count": 24 * 30,
}

NEIGHBOR_WINDOW_FEATURE = "previous_24h_count"


@dataclass(frozen=True)
class FireHistoryFeatures:
    tile_id: str
    cutoff: datetime
    previous_24h_count: int
    previous_72h_count: int
    previous_7d_count: int
    previous_30d_count: int
    neighboring_previous_24h_count: int


def compute_fire_history_features(
    observations: list[Observation],
    cells: list[GridCell],
    cutoffs: list[datetime],
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> list[FireHistoryFeatures]:
    """`bbox`/`resolution_deg` must match whatever `cells` was built with,
    same as `construct_labels`."""
    qualifying = [obs for obs in observations if is_qualifying_observation(obs)]

    observations_with_tile = [
        (obs, tile_id)
        for obs in qualifying
        if (tile_id := locate_tile(obs.latitude, obs.longitude, bbox, resolution_deg))
        is not None
    ]

    neighbors_by_tile = {
        cell.tile_id: neighbor_tile_ids(
            cell.lat_index, cell.lon_index, bbox, resolution_deg
        )
        for cell in cells
    }

    records: list[FireHistoryFeatures] = []

    for cutoff in cutoffs:
        counts_by_window: dict[str, dict[str, int]] = {}

        for feature_name, window_hours in FIRE_HISTORY_WINDOWS_HOURS.items():
            window_start = cutoff - timedelta(hours=window_hours)
            tile_counts: dict[str, int] = {}

            for obs, tile_id in observations_with_tile:
                if window_start < obs.observed_at <= cutoff:
                    tile_counts[tile_id] = tile_counts.get(tile_id, 0) + 1

            counts_by_window[feature_name] = tile_counts

        neighbor_source_counts = counts_by_window[NEIGHBOR_WINDOW_FEATURE]

        for cell in cells:
            neighboring_count = sum(
                neighbor_source_counts.get(neighbor_id, 0)
                for neighbor_id in neighbors_by_tile[cell.tile_id]
            )

            records.append(
                FireHistoryFeatures(
                    tile_id=cell.tile_id,
                    cutoff=cutoff,
                    previous_24h_count=counts_by_window["previous_24h_count"].get(
                        cell.tile_id, 0
                    ),
                    previous_72h_count=counts_by_window["previous_72h_count"].get(
                        cell.tile_id, 0
                    ),
                    previous_7d_count=counts_by_window["previous_7d_count"].get(
                        cell.tile_id, 0
                    ),
                    previous_30d_count=counts_by_window["previous_30d_count"].get(
                        cell.tile_id, 0
                    ),
                    neighboring_previous_24h_count=neighboring_count,
                )
            )

    return records


def save_fire_history_features(
    records: list[FireHistoryFeatures], output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(
            "tile_id,cutoff,previous_24h_count,previous_72h_count,"
            "previous_7d_count,previous_30d_count,neighboring_previous_24h_count\n"
        )

        for record in records:
            handle.write(
                f"{record.tile_id},{record.cutoff.isoformat()},"
                f"{record.previous_24h_count},{record.previous_72h_count},"
                f"{record.previous_7d_count},{record.previous_30d_count},"
                f"{record.neighboring_previous_24h_count}\n"
            )

    return output_path
