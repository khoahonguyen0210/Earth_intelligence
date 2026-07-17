from __future__ import annotations

import math
from dataclasses import dataclass

from sklearn.linear_model import LogisticRegression

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

# Regularization strengths tried during validation-only tuning.
C_CANDIDATES: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0)


@dataclass(frozen=True)
class LogisticRegressionResult:
    model: LogisticRegression
    preprocessor: Preprocessor
    selected_c: float
    validation_pr_auc: float


def fit_logistic_regression(
    train_rows: list[DatasetRow], validation_rows: list[DatasetRow]
) -> LogisticRegressionResult:
    y_train = extract_targets(train_rows)
    observed_classes = sorted(set(y_train.tolist()))

    if len(observed_classes) < 2:
        raise ValueError(
            "cannot fit logistic regression: the training split contains "
            f"only one class (target values seen: {observed_classes}). This "
            "means no real historical positive examples exist in the "
            "training split yet -- not a bug, a real data-availability gap."
        )

    preprocessor = fit_preprocessor(train_rows)
    x_train = transform(preprocessor, train_rows)

    x_validation = transform(preprocessor, validation_rows)
    y_validation = extract_targets(validation_rows).tolist()

    best_c = C_CANDIDATES[0]
    best_score = float("-inf")

    for c in C_CANDIDATES:
        candidate = LogisticRegression(C=c, max_iter=1000, class_weight="balanced")
        candidate.fit(x_train, y_train)

        validation_predictions = candidate.predict_proba(x_validation)[:, 1].tolist()
        validation_metrics = compute_metrics(y_validation, validation_predictions)

        if not math.isnan(validation_metrics.pr_auc) and (
            validation_metrics.pr_auc > best_score
        ):
            best_score = validation_metrics.pr_auc
            best_c = c

    if best_score == float("-inf"):
        # Validation split also has no positives to score against; keep
        # the smallest candidate as a defined, deterministic fallback
        # rather than silently picking an arbitrary one.
        best_score = float("nan")

    final_model = LogisticRegression(C=best_c, max_iter=1000, class_weight="balanced")
    final_model.fit(x_train, y_train)

    return LogisticRegressionResult(
        model=final_model,
        preprocessor=preprocessor,
        selected_c=best_c,
        validation_pr_auc=best_score,
    )


def predict_logistic_regression(
    result: LogisticRegressionResult, rows: list[DatasetRow]
) -> list[float]:
    x = transform(result.preprocessor, rows)

    return result.model.predict_proba(x)[:, 1].tolist()


def evaluate_logistic_regression(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
) -> tuple[LogisticRegressionResult, list[float], ClassificationMetrics]:
    result = fit_logistic_regression(train_rows, validation_rows)
    predictions = predict_logistic_regression(result, test_rows)
    y_true = [row.target for row in test_rows]
    metrics = compute_metrics(y_true, predictions)

    return result, predictions, metrics
