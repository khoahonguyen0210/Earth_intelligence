from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from xgboost import DMatrix

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CalibratedModel,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    feature_names,
    transform,
)

EXPLANATION_METHOD = "xgboost_tree_shap"
EXPLANATION_UNITS = "log_odds"
TOP_DRIVERS_PER_CELL = 3
LAND_COVER_PREFIX = "land_cover_"


@dataclass(frozen=True)
class FeatureContribution:
    feature: str
    contribution: float


@dataclass(frozen=True)
class Contributions:
    features: tuple[str, ...]
    values: np.ndarray
    bias: np.ndarray


def _grouped_feature_names(names: list[str]) -> list[str]:
    return [
        "land_cover" if name.startswith(LAND_COVER_PREFIX) else name for name in names
    ]


def _iteration_range(model: CalibratedModel) -> tuple[int, int]:
    best_iteration = model.base_result.model.best_iteration
    if best_iteration is None:
        return (0, 0)
    return (0, best_iteration + 1)


def compute_contributions(
    model: CalibratedModel, rows: list[DatasetRow]
) -> Contributions:
    preprocessor = model.base_result.preprocessor
    x = transform(preprocessor, rows)
    booster = model.base_result.model.get_booster()
    raw = booster.predict(
        DMatrix(x), pred_contribs=True, iteration_range=_iteration_range(model)
    )

    names = _grouped_feature_names(
        feature_names(preprocessor.feature_columns, preprocessor.include_land_cover)
    )
    groups = list(dict.fromkeys(names))
    grouped = np.zeros((raw.shape[0], len(groups)), dtype=float)
    for column, name in enumerate(names):
        grouped[:, groups.index(name)] += raw[:, column]

    return Contributions(features=tuple(groups), values=grouped, bias=raw[:, -1])


def top_drivers(
    features: tuple[str, ...], row: np.ndarray, k: int = TOP_DRIVERS_PER_CELL
) -> tuple[FeatureContribution, ...]:
    order = np.argsort(-np.abs(row), kind="stable")
    return tuple(
        FeatureContribution(feature=features[index], contribution=float(row[index]))
        for index in order[:k]
        if row[index] != 0.0
    )


def mean_absolute_importance(
    contributions: Contributions,
) -> tuple[FeatureContribution, ...]:
    if contributions.values.shape[0] == 0:
        return ()
    means = np.abs(contributions.values).mean(axis=0)
    order = np.argsort(-means, kind="stable")
    return tuple(
        FeatureContribution(
            feature=contributions.features[index], contribution=float(means[index])
        )
        for index in order
    )
