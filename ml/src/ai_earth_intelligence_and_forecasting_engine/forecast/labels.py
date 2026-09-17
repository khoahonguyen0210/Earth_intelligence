from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridCell,
    locate_tile,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    FORECAST_WINDOW_HOURS,
)

LABEL_DATASET_VERSION = "v1"


@dataclass(frozen=True)
class LabelRecord:
    tile_id: str
    cutoff: datetime
    target: int
    qualifying_observation_ids: tuple[str, ...]


def is_qualifying_observation(observation: Observation) -> bool:
    """Whether an observation counts as fire evidence for labeling.

    Confidence is not required to be present; only an explicit "l"
    disqualifies.
    """
    if not -90 <= observation.latitude <= 90:
        return False

    if not -180 <= observation.longitude <= 180:
        return False

    if observation.observed_at is None or observation.observed_at.tzinfo is None:
        return False

    if observation.confidence is not None and observation.confidence.lower() == "l":
        return False

    return True


def hourly_cutoffs(start: datetime, end: datetime) -> list[datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")

    cutoffs: list[datetime] = []
    current = start

    while current < end:
        cutoffs.append(current)
        current += timedelta(hours=1)

    return cutoffs


def construct_labels(
    observations: list[Observation],
    cells: list[GridCell],
    cutoffs: list[datetime],
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> list[LabelRecord]:
    """`bbox`/`resolution_deg` must match whatever `cells` was built with
    (they default to the same values `build_california_grid` defaults to),
    so that tile IDs computed here for each observation line up with the
    tile IDs already on `cells`."""
    qualifying = [obs for obs in observations if is_qualifying_observation(obs)]

    records: list[LabelRecord] = []

    for cutoff in cutoffs:
        window_end = cutoff + timedelta(hours=FORECAST_WINDOW_HOURS)

        # Half-open on the near side, closed on the far side: (cutoff, window_end].
        window_observations = [
            obs for obs in qualifying if cutoff < obs.observed_at <= window_end
        ]

        observations_by_tile: dict[str, list[str]] = {}
        for obs in window_observations:
            tile_id = locate_tile(obs.latitude, obs.longitude, bbox, resolution_deg)

            if tile_id is None:
                continue

            observations_by_tile.setdefault(tile_id, []).append(obs.observation_id)

        for cell in cells:
            matching_ids = tuple(observations_by_tile.get(cell.tile_id, []))

            records.append(
                LabelRecord(
                    tile_id=cell.tile_id,
                    cutoff=cutoff,
                    target=1 if matching_ids else 0,
                    qualifying_observation_ids=matching_ids,
                )
            )

    return records


def save_labels(records: list[LabelRecord], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("tile_id,cutoff,target,qualifying_observation_ids\n")

        for record in records:
            observation_ids = "|".join(record.qualifying_observation_ids)
            handle.write(
                f"{record.tile_id},{record.cutoff.isoformat()},"
                f"{record.target},{observation_ids}\n"
            )

    return output_path
