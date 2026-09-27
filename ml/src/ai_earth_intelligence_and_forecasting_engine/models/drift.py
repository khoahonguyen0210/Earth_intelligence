from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    LAND_COVER_CLASSES,
    NUMERIC_FEATURE_COLUMNS,
)

N_BINS = 10
PSI_MODERATE = 0.1
PSI_MAJOR = 0.25
REFERENCE_FILE = "feature_reference.json"
_FLOOR = 1e-4


def save_reference(reference: dict[str, Any], model_dir: Path) -> Path:
    path = model_dir / REFERENCE_FILE
    path.write_text(json.dumps(reference, indent=2), encoding="utf-8")
    return path


def load_reference(model_dir: Path) -> dict[str, Any] | None:
    path = model_dir / REFERENCE_FILE
    if not path.exists():
        return None
    reference: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return reference


def _numeric_values(rows: list[DatasetRow], column: str) -> np.ndarray:
    values = [getattr(row, column) for row in rows]
    return np.array(
        [math.nan if value is None else value for value in values], dtype=float
    )


def _numeric_proportions(values: np.ndarray, edges: tuple[float, ...]) -> list[float]:
    """Bins are (-inf, e1], (e1, e2], ..., (ek, inf), plus one missing bin."""
    present = values[~np.isnan(values)]
    counts = np.bincount(
        np.searchsorted(np.array(edges), present, side="left"),
        minlength=len(edges) + 1,
    ).tolist()
    counts.append(int(np.isnan(values).sum()))
    total = max(len(values), 1)
    return [count / total for count in counts]


def _land_cover_proportions(rows: list[DatasetRow]) -> list[float]:
    keys = [*LAND_COVER_CLASSES, None]
    counts = [0] * len(keys)
    for row in rows:
        value = row.land_cover_class
        counts[keys.index(value) if value in LAND_COVER_CLASSES else -1] += 1
    total = max(len(rows), 1)
    return [count / total for count in counts]


def build_reference(rows: list[DatasetRow], n_bins: int = N_BINS) -> dict[str, Any]:
    """The training distribution each serving batch is compared against:
    quantile bin edges and the share of rows in each bin per numeric
    feature (count features are mostly zero, so their edges collapse to
    a few distinct values), and class shares for land cover."""
    reference: dict[str, Any] = {}
    for column in NUMERIC_FEATURE_COLUMNS:
        values = _numeric_values(rows, column)
        present = values[~np.isnan(values)]
        quantiles = (
            np.quantile(present, np.linspace(0, 1, n_bins + 1)[1:-1])
            if len(present)
            else np.array([])
        )
        edges = tuple(float(edge) for edge in np.unique(quantiles))
        reference[column] = {
            "edges": list(edges),
            "proportions": _numeric_proportions(values, edges),
        }
    reference["land_cover_class"] = {
        "edges": [],
        "proportions": _land_cover_proportions(rows),
    }
    return {"n_rows": len(rows), "features": reference}


def psi(expected: list[float], actual: list[float]) -> float:
    """Population stability index. Under 0.1 is stable, 0.1 to 0.25 a
    moderate shift, above 0.25 a major one."""
    total = 0.0
    for e, a in zip(expected, actual, strict=True):
        e, a = max(e, _FLOOR), max(a, _FLOOR)
        total += (a - e) * math.log(a / e)
    return total


WEATHER_FEATURES: frozenset[str] = frozenset({
    "temperature_2m",
    "total_precipitation",
    "u_wind_10m",
    "v_wind_10m",
    "relative_humidity",
})

SERVING_DRIFT_FEATURES: tuple[str, ...] = tuple(
    column
    for column in (*NUMERIC_FEATURE_COLUMNS, "land_cover_class")
    if column not in WEATHER_FEATURES
)


def drift_report(
    reference: dict[str, Any],
    rows: list[DatasetRow],
    columns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """PSI of `rows` against the training reference, per feature.

    A single forecast holds one day of weather for every cell, and the
    reference pools a whole training season, so its weather always
    looks shifted. Serving therefore checks SERVING_DRIFT_FEATURES only;
    weather drift is checked over a season of rows instead."""
    scores: dict[str, float] = {}
    for column, entry in reference["features"].items():
        if columns is not None and column not in columns:
            continue
        if column == "land_cover_class":
            actual = _land_cover_proportions(rows)
        else:
            actual = _numeric_proportions(
                _numeric_values(rows, column), tuple(entry["edges"])
            )
        scores[column] = round(psi(entry["proportions"], actual), 4)

    return {
        "psi": scores,
        "max_psi": max(scores.values()) if scores else 0.0,
        "moderate": sorted(
            name for name, value in scores.items() if PSI_MODERATE <= value < PSI_MAJOR
        ),
        "major": sorted(name for name, value in scores.items() if value >= PSI_MAJOR),
    }
