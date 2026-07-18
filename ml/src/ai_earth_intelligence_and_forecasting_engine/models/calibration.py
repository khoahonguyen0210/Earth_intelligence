from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: never try to open a display window

import matplotlib.pyplot as plt  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.frozen import FrozenEstimator  # noqa: E402

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (  # noqa: E402
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (  # noqa: E402
    ClassificationMetrics,
    compute_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (  # noqa: E402
    extract_targets,
    transform,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (  # noqa: E402
    XGBoostResult,
)

MODEL_VERSION = "v1"
CALIBRATION_METHOD = "isotonic"
N_CALIBRATION_BINS = 10


@dataclass(frozen=True)
class CalibratedModel:
    calibrated_classifier: CalibratedClassifierCV
    base_result: XGBoostResult


@dataclass(frozen=True)
class CalibrationBin:
    bin_index: int
    predicted_mean: float
    observed_frequency: float
    count: int


def fit_calibration(
    base_result: XGBoostResult, validation_rows: list[DatasetRow]
) -> CalibratedModel:
    """Calibrates an already-fit model's probabilities using validation
    data only -- the base model (fit on train, tuned via validation early
    stopping in Task 4.3) is frozen and never refit here."""
    y_validation = extract_targets(validation_rows)
    validation_classes = sorted(set(y_validation.tolist()))

    if len(validation_classes) < 2:
        raise ValueError(
            "cannot fit calibration: the validation split contains only "
            f"one class (target values seen: {validation_classes}). "
            "Calibration needs both classes present in validation to "
            "learn a meaningful probability mapping."
        )

    x_validation = transform(base_result.preprocessor, validation_rows)

    frozen = FrozenEstimator(base_result.model)
    calibrated_classifier = CalibratedClassifierCV(
        estimator=frozen, method=CALIBRATION_METHOD
    )
    calibrated_classifier.fit(x_validation, y_validation)

    return CalibratedModel(
        calibrated_classifier=calibrated_classifier, base_result=base_result
    )


def predict_calibrated(model: CalibratedModel, rows: list[DatasetRow]) -> list[float]:
    x = transform(model.base_result.preprocessor, rows)

    return model.calibrated_classifier.predict_proba(x)[:, 1].tolist()


def build_calibration_table(
    y_true: list[int], y_pred_proba: list[float], n_bins: int = N_CALIBRATION_BINS
) -> list[CalibrationBin]:
    if len(y_true) != len(y_pred_proba):
        raise ValueError("y_true and y_pred_proba must be the same length")

    bins: list[list[tuple[int, float]]] = [[] for _ in range(n_bins)]

    for target, prediction in zip(y_true, y_pred_proba):
        bin_index = min(int(prediction * n_bins), n_bins - 1)
        bins[bin_index].append((target, prediction))

    table: list[CalibrationBin] = []

    for bin_index, entries in enumerate(bins):
        if not entries:
            continue

        targets = [target for target, _ in entries]
        predictions = [prediction for _, prediction in entries]

        table.append(
            CalibrationBin(
                bin_index=bin_index,
                predicted_mean=sum(predictions) / len(predictions),
                observed_frequency=sum(targets) / len(targets),
                count=len(entries),
            )
        )

    return table


def save_calibration_table(table: list[CalibrationBin], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("bin_index,predicted_mean,observed_frequency,count\n")

        for entry in table:
            handle.write(
                f"{entry.bin_index},{entry.predicted_mean},"
                f"{entry.observed_frequency},{entry.count}\n"
            )

    return output_path


def plot_reliability_diagram(table: list[CalibrationBin], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    figure, axes = plt.subplots(figsize=(5, 5))
    axes.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect calibration")

    if table:
        predicted = [entry.predicted_mean for entry in table]
        observed = [entry.observed_frequency for entry in table]
        axes.plot(predicted, observed, marker="o", color="#2563eb", label="Model")

    axes.set_xlabel("Mean predicted probability")
    axes.set_ylabel("Observed frequency")
    axes.set_title("Reliability diagram")
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)
    axes.legend()

    figure.tight_layout()
    figure.savefig(output_path)
    plt.close(figure)

    return output_path


def evaluate_calibration(
    base_result: XGBoostResult,
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
) -> tuple[CalibratedModel, list[float], ClassificationMetrics, list[CalibrationBin]]:
    model = fit_calibration(base_result, validation_rows)
    predictions = predict_calibrated(model, test_rows)
    y_true = [row.target for row in test_rows]
    metrics = compute_metrics(y_true, predictions)
    table = build_calibration_table(y_true, predictions)

    return model, predictions, metrics, table
