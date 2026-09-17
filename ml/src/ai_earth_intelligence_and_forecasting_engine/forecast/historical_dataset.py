from __future__ import annotations

import bisect
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    ERA5Record,
    parse_era5_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.geography import GeographyCell
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridCell,
)
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    era5_file_name,
    observation_window,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
    build_dataset,
)


class ObservationIndex:
    """Observations sorted by time, sliceable by a half-open window."""

    def __init__(self, observations: list[Observation]):
        timed = [obs for obs in observations if obs.observed_at is not None]
        self._observations = sorted(timed, key=lambda obs: obs.observed_at)
        self._times = [obs.observed_at for obs in self._observations]

    def __len__(self) -> int:
        return len(self._observations)

    def between(self, start: datetime, end: datetime) -> list[Observation]:
        """start < observed_at <= end -- the same (open, closed] convention
        every label and fire-history window uses."""
        low = bisect.bisect_right(self._times, start)
        high = bisect.bisect_right(self._times, end)
        return self._observations[low:high]


def iter_historical_rows(
    observations: ObservationIndex,
    era5_for_cutoff: Callable[[datetime], list[ERA5Record]],
    geography_cells: list[GeographyCell],
    cells: list[GridCell],
    cutoffs: list[datetime],
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> Iterator[list[DatasetRow]]:
    """Yields each cutoff's rows (one per cell), in cutoff order, so a
    caller can stream them to disk instead of holding every row."""
    for cutoff in sorted(cutoffs):
        start, end = observation_window(cutoff)
        yield build_dataset(
            observations.between(start, end),
            era5_for_cutoff(cutoff),
            geography_cells,
            cells,
            [cutoff],
            bbox=bbox,
            resolution_deg=resolution_deg,
        )


class ERA5History:
    """ERA5-Land records from the per-month history files, parsed lazily.

    A cutoff's lookback can reach into the previous month (a July 2
    cutoff's latest record may be June 29), so each lookup reads the
    cutoff's month and the one before it. Only those two months stay
    parsed."""

    def __init__(self, history_dir: Path):
        self._history_dir = history_dir
        self._months: dict[tuple[int, int], list[ERA5Record]] = {}

    def _month(self, year: int, month: int) -> list[ERA5Record]:
        key = (year, month)
        if key not in self._months:
            path = self._history_dir / era5_file_name(year, month)
            self._months[key] = parse_era5_records(path) if path.exists() else []
        return self._months[key]

    def for_cutoff(self, cutoff: datetime) -> list[ERA5Record]:
        """Records in the cutoff's lookback with valid_time <= cutoff."""
        current = (cutoff.year, cutoff.month)
        previous = (cutoff.year - 1, 12) if cutoff.month == 1 else (cutoff.year, cutoff.month - 1)
        for key in list(self._months):
            if key not in (current, previous):
                del self._months[key]

        start, _ = observation_window(cutoff)
        return [
            record
            for key in (previous, current)
            for record in self._month(*key)
            if start < record.valid_time <= cutoff
        ]
