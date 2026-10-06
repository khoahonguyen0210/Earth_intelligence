from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import average_precision_score

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)

BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_SEED = 20241004
SPATIAL_BLOCK_CELLS = 10
SPATIAL_FOLDS = 5


def persistence_scores(rows: list[DatasetRow], window: str = "7d") -> list[float]:
    column = {"24h": "previous_24h_count", "7d": "previous_7d_count"}[window]
    return [
        float(getattr(row, column)) + row.previous_30d_count * 1e-3 for row in rows
    ]


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float


def _pr_auc(y: np.ndarray, scores: np.ndarray) -> float:
    if y.sum() == 0 or y.sum() == len(y):
        return float("nan")
    return float(average_precision_score(y, scores))


def block_bootstrap(
    y_true: np.ndarray,
    scores: dict[str, np.ndarray],
    groups: np.ndarray,
    baseline: str,
    n_samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[dict[str, Interval], dict[str, Interval]]:
    rng = np.random.default_rng(seed)
    unique_groups = np.unique(groups)
    index_by_group = {group: np.flatnonzero(groups == group) for group in unique_groups}

    draws: dict[str, list[float]] = {name: [] for name in scores}
    for _ in range(n_samples):
        chosen = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        index = np.concatenate([index_by_group[group] for group in chosen])
        for name, values in scores.items():
            draws[name].append(_pr_auc(y_true[index], values[index]))

    def interval(point: float, samples: np.ndarray) -> Interval:
        low, high = np.nanpercentile(samples, [2.5, 97.5])
        return Interval(estimate=point, low=float(low), high=float(high))

    points = {name: _pr_auc(y_true, values) for name, values in scores.items()}
    metric = {
        name: interval(points[name], np.array(samples))
        for name, samples in draws.items()
    }
    baseline_draws = np.array(draws[baseline])
    difference = {
        name: interval(
            points[name] - points[baseline], np.array(samples) - baseline_draws
        )
        for name, samples in draws.items()
        if name != baseline
    }
    return metric, difference


def tile_indices(tile_id: str) -> tuple[int, int]:
    _, lat, lon = tile_id.split("_")
    return int(lat), int(lon)


def spatial_fold(
    tile_id: str,
    block_cells: int = SPATIAL_BLOCK_CELLS,
    n_folds: int = SPATIAL_FOLDS,
) -> int:
    lat, lon = tile_indices(tile_id)
    block_lat, block_lon = lat // block_cells, lon // block_cells
    return (block_lat * 2 + block_lon) % n_folds
