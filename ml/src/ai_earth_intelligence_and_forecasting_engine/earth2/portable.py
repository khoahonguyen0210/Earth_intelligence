from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import xgboost

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CalibratedModel,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    LAND_COVER_CLASSES,
)

FORMAT_VERSION = 1


def export_model(model: CalibratedModel) -> dict[str, Any]:
    base = model.base_result
    preprocessor = base.preprocessor
    calibrators = model.calibrated_classifier.calibrated_classifiers_
    if len(calibrators) != 1:
        raise ValueError("expected one isotonic calibrator")
    isotonic = calibrators[0].calibrators[0]
    return {
        "format_version": FORMAT_VERSION,
        "feature_columns": list(preprocessor.feature_columns),
        "include_land_cover": preprocessor.include_land_cover,
        "land_cover_classes": list(LAND_COVER_CLASSES),
        "impute_values": preprocessor.imputer.statistics_.tolist(),
        "scale_mean": preprocessor.scaler.mean_.tolist(),
        "scale_std": preprocessor.scaler.scale_.tolist(),
        "best_iteration": int(base.best_iteration),
        "booster": bytes(base.model.get_booster().save_raw("json")).decode("utf-8"),
        "isotonic_x": isotonic.X_thresholds_.tolist(),
        "isotonic_y": isotonic.y_thresholds_.tolist(),
    }


def feature_matrix(model: dict[str, Any], rows: Sequence[DatasetRow]) -> np.ndarray:
    numeric = np.array(
        [
            [
                np.nan if getattr(row, column) is None else getattr(row, column)
                for column in model["feature_columns"]
            ]
            for row in rows
        ],
        dtype=float,
    ).reshape(len(rows), len(model["feature_columns"]))
    numeric = np.where(np.isnan(numeric), np.array(model["impute_values"]), numeric)
    numeric = (numeric - np.array(model["scale_mean"])) / np.array(model["scale_std"])
    if not model["include_land_cover"]:
        return numeric
    classes = model["land_cover_classes"]
    one_hot = np.zeros((len(rows), len(classes)))
    for index, row in enumerate(rows):
        if row.land_cover_class in classes:
            one_hot[index, classes.index(row.land_cover_class)] = 1.0
    return np.hstack([numeric, one_hot])


def predict(model: dict[str, Any], rows: Sequence[DatasetRow]) -> np.ndarray:
    if model.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported model format")
    booster = xgboost.Booster()
    booster.load_model(bytearray(model["booster"], "utf-8"))
    raw = booster.predict(
        xgboost.DMatrix(feature_matrix(model, rows)),
        iteration_range=(0, model["best_iteration"] + 1),
    )
    return np.interp(raw, model["isotonic_x"], model["isotonic_y"])
