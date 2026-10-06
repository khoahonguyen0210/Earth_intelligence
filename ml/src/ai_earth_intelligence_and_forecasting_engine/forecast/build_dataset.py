from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from ai_earth_intelligence_and_forecasting_engine.data.era5 import ERA5Record
from ai_earth_intelligence_and_forecasting_engine.data.geography import GeographyCell
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridCell,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    environmental_features as ef,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    fire_history_features as fhf,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    geography_features as gf,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import labels as lb
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    TEST_SPLIT,
    TRAIN_SPLIT,
    VALIDATION_SPLIT,
    split_for_date,
)

DATASET_VERSION = "v1"
FEATURE_VERSION = "v1"

FEATURE_COLUMNS: tuple[str, ...] = (
    "previous_24h_count",
    "previous_72h_count",
    "previous_7d_count",
    "previous_30d_count",
    "neighboring_previous_24h_count",
    "temperature_2m",
    "total_precipitation",
    "u_wind_10m",
    "v_wind_10m",
    "relative_humidity",
    "elevation_m",
    "slope_deg",
    "land_cover_class",
)


@dataclass(frozen=True)
class DatasetRow:
    tile_id: str
    cutoff: datetime
    split: str
    target: int
    previous_24h_count: int
    previous_72h_count: int
    previous_7d_count: int
    previous_30d_count: int
    neighboring_previous_24h_count: int
    temperature_2m: float | None
    total_precipitation: float | None
    u_wind_10m: float | None
    v_wind_10m: float | None
    relative_humidity: float | None
    elevation_m: float | None
    slope_deg: float | None
    land_cover_class: int | None


def build_dataset(
    observations: list[Observation],
    era5_records: list[ERA5Record],
    geography_cells: list[GeographyCell],
    cells: list[GridCell],
    cutoffs: list[datetime],
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    resolution_deg: float = GRID_RESOLUTION_DEG,
) -> list[DatasetRow]:
    labels_by_key = {
        (record.tile_id, record.cutoff): record
        for record in lb.construct_labels(
            observations, cells, cutoffs, bbox, resolution_deg
        )
    }
    fire_history_by_key = {
        (record.tile_id, record.cutoff): record
        for record in fhf.compute_fire_history_features(
            observations, cells, cutoffs, bbox, resolution_deg
        )
    }
    environmental_by_key = {
        (record.tile_id, record.cutoff): record
        for record in ef.compute_environmental_features(
            era5_records, cells, cutoffs, bbox, resolution_deg
        )
    }
    geography_by_tile = {
        record.tile_id: record
        for record in gf.compute_geography_features(
            geography_cells, cells, bbox, resolution_deg
        )
    }

    rows: list[DatasetRow] = []

    for cutoff in cutoffs:
        split = split_for_date(cutoff.date()) or "unassigned"

        for cell in cells:
            key = (cell.tile_id, cutoff)
            label = labels_by_key[key]
            fire_history = fire_history_by_key[key]
            environmental = environmental_by_key[key]
            geography = geography_by_tile[cell.tile_id]

            rows.append(
                DatasetRow(
                    tile_id=cell.tile_id,
                    cutoff=cutoff,
                    split=split,
                    target=label.target,
                    previous_24h_count=fire_history.previous_24h_count,
                    previous_72h_count=fire_history.previous_72h_count,
                    previous_7d_count=fire_history.previous_7d_count,
                    previous_30d_count=fire_history.previous_30d_count,
                    neighboring_previous_24h_count=(
                        fire_history.neighboring_previous_24h_count
                    ),
                    temperature_2m=environmental.temperature_2m,
                    total_precipitation=environmental.total_precipitation,
                    u_wind_10m=environmental.u_wind_10m,
                    v_wind_10m=environmental.v_wind_10m,
                    relative_humidity=environmental.relative_humidity,
                    elevation_m=geography.elevation_m,
                    slope_deg=geography.slope_deg,
                    land_cover_class=geography.land_cover_class,
                )
            )

    return rows


@dataclass(frozen=True)
class DatasetManifest:
    dataset_version: str
    feature_version: str
    split_dates: dict[str, dict[str, str]]
    row_counts: dict[str, int]
    positive_rates: dict[str, float]
    feature_schema: list[str]
    generated_at: str


def build_dataset_manifest(rows: list[DatasetRow]) -> DatasetManifest:
    row_counts: dict[str, int] = {}
    positive_counts: dict[str, int] = {}

    for row in rows:
        row_counts[row.split] = row_counts.get(row.split, 0) + 1

        if row.target == 1:
            positive_counts[row.split] = positive_counts.get(row.split, 0) + 1

    positive_rates = {
        split: positive_counts.get(split, 0) / count
        for split, count in row_counts.items()
    }

    return DatasetManifest(
        dataset_version=DATASET_VERSION,
        feature_version=FEATURE_VERSION,
        split_dates={
            "train": {
                "start": TRAIN_SPLIT.start.isoformat(),
                "end": TRAIN_SPLIT.end.isoformat(),
            },
            "validation": {
                "start": VALIDATION_SPLIT.start.isoformat(),
                "end": VALIDATION_SPLIT.end.isoformat(),
            },
            "test": {
                "start": TEST_SPLIT.start.isoformat(),
                "end": TEST_SPLIT.end.isoformat(),
            },
        },
        row_counts={**row_counts, "total": len(rows)},
        positive_rates=positive_rates,
        feature_schema=list(FEATURE_COLUMNS),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


DATASET_HEADER = "tile_id,cutoff,split,target," + ",".join(FEATURE_COLUMNS)

INTEGER_COLUMNS = frozenset(
    {
        "previous_24h_count",
        "previous_72h_count",
        "previous_7d_count",
        "previous_30d_count",
        "neighboring_previous_24h_count",
        "land_cover_class",
    }
)


def write_dataset_rows(handle: TextIO, rows: Iterable[DatasetRow]) -> None:
    for row in rows:
        values = [
            row.tile_id,
            row.cutoff.isoformat(),
            row.split,
            str(row.target),
            *(str(getattr(row, column)) for column in FEATURE_COLUMNS),
        ]
        handle.write(",".join(values) + "\n")


def save_dataset(rows: list[DatasetRow], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(DATASET_HEADER + "\n")
        write_dataset_rows(handle, rows)

    return output_path


def load_dataset(path: Path) -> list[DatasetRow]:
    def parse(column: str, value: str) -> int | float | None:
        if value == "None":
            return None
        return int(value) if column in INTEGER_COLUMNS else float(value)

    with path.open(encoding="utf-8") as handle:
        return [
            DatasetRow(
                tile_id=record["tile_id"],
                cutoff=datetime.fromisoformat(record["cutoff"]),
                split=record["split"],
                target=int(record["target"]),
                **{column: parse(column, record[column]) for column in FEATURE_COLUMNS},  # type: ignore[arg-type]
            )
            for record in csv.DictReader(handle)
        ]


def save_dataset_manifest(manifest: DatasetManifest, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")

    return output_path


def manifest_to_dict(manifest: DatasetManifest) -> dict[str, Any]:
    return asdict(manifest)
