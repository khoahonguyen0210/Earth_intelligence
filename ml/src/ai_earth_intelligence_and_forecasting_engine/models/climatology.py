from __future__ import annotations

from dataclasses import dataclass

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    ClassificationMetrics,
    compute_metrics,
)

MODEL_VERSION = "v1"


@dataclass(frozen=True)
class ClimatologyModel:
    """Per-tile historical fire-occurrence rate, fit on training data only.

    Transparent by construction: the "prediction" for a tile is exactly
    its observed positive rate during training, with no other features
    involved. Falls back to the training set's overall rate for any tile
    never seen in training.
    """

    tile_rates: dict[str, float]
    global_rate: float


def fit_climatology(train_rows: list[DatasetRow]) -> ClimatologyModel:
    if not train_rows:
        raise ValueError("cannot fit climatology on an empty training set")

    tile_totals: dict[str, int] = {}
    tile_positives: dict[str, int] = {}

    for row in train_rows:
        tile_totals[row.tile_id] = tile_totals.get(row.tile_id, 0) + 1
        tile_positives[row.tile_id] = tile_positives.get(row.tile_id, 0) + row.target

    tile_rates = {
        tile_id: tile_positives[tile_id] / tile_totals[tile_id]
        for tile_id in tile_totals
    }

    global_rate = sum(row.target for row in train_rows) / len(train_rows)

    return ClimatologyModel(tile_rates=tile_rates, global_rate=global_rate)


def predict_climatology(
    model: ClimatologyModel, rows: list[DatasetRow]
) -> list[float]:
    return [model.tile_rates.get(row.tile_id, model.global_rate) for row in rows]


def evaluate_climatology(
    train_rows: list[DatasetRow], test_rows: list[DatasetRow]
) -> tuple[ClimatologyModel, list[float], ClassificationMetrics]:
    model = fit_climatology(train_rows)
    predictions = predict_climatology(model, test_rows)
    y_true = [row.target for row in test_rows]
    metrics = compute_metrics(y_true, predictions)

    return model, predictions, metrics
