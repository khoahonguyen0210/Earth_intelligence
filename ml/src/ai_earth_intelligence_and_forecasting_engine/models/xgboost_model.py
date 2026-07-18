from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xgboost import XGBClassifier

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    ClassificationMetrics,
    compute_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    Preprocessor,
    extract_targets,
    fit_preprocessor,
    transform,
)

MODEL_VERSION = "v1"

# One fixed, documented base configuration (Task 4.3: "start from one
# fixed documented configuration"). max_depth/learning_rate/subsample are
# standard, conservative starting points for a small-to-medium tabular
# binary classification problem. n_estimators is only an upper cap -- the
# actual number of trees used is chosen via early stopping against the
# validation set (see fit_xgboost), which is the "tune only against
# validation data" step for this model.
BASE_CONFIG: dict[str, Any] = {
    "n_estimators": 500,
    "max_depth": 4,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "random_state": 20240815,
}

EARLY_STOPPING_ROUNDS = 10


@dataclass(frozen=True)
class XGBoostResult:
    model: XGBClassifier
    preprocessor: Preprocessor
    best_iteration: int
    config: dict[str, Any]


def fit_xgboost(
    train_rows: list[DatasetRow], validation_rows: list[DatasetRow]
) -> XGBoostResult:
    y_train = extract_targets(train_rows)
    train_classes = sorted(set(y_train.tolist()))

    if len(train_classes) < 2:
        raise ValueError(
            "cannot fit XGBoost: the training split contains only one "
            f"class (target values seen: {train_classes}). This means no "
            "real historical positive examples exist in the training "
            "split yet -- not a bug, a real data-availability gap."
        )

    y_validation = extract_targets(validation_rows)
    validation_classes = sorted(set(y_validation.tolist()))

    if len(validation_classes) < 2:
        raise ValueError(
            "cannot tune XGBoost via early stopping: the validation split "
            f"contains only one class (target values seen: "
            f"{validation_classes}). Early stopping needs both classes "
            "present in validation to measure meaningful progress."
        )

    preprocessor = fit_preprocessor(train_rows)
    x_train = transform(preprocessor, train_rows)
    x_validation = transform(preprocessor, validation_rows)

    model = XGBClassifier(**BASE_CONFIG, early_stopping_rounds=EARLY_STOPPING_ROUNDS)
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_validation, y_validation)],
        verbose=False,
    )

    best_iteration = (
        model.best_iteration
        if model.best_iteration is not None
        else BASE_CONFIG["n_estimators"]
    )

    return XGBoostResult(
        model=model,
        preprocessor=preprocessor,
        best_iteration=best_iteration,
        config=dict(BASE_CONFIG),
    )


def predict_xgboost(result: XGBoostResult, rows: list[DatasetRow]) -> list[float]:
    x = transform(result.preprocessor, rows)

    return result.model.predict_proba(x)[:, 1].tolist()


def evaluate_xgboost(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
) -> tuple[XGBoostResult, list[float], ClassificationMetrics]:
    result = fit_xgboost(train_rows, validation_rows)
    predictions = predict_xgboost(result, test_rows)
    y_true = [row.target for row in test_rows]
    metrics = compute_metrics(y_true, predictions)

    return result, predictions, metrics
