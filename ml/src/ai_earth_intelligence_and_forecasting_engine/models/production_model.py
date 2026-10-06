from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CALIBRATION_METHOD,
    MODEL_VERSION,
    CalibratedModel,
    CalibrationBin,
    build_calibration_table,
    fit_calibration,
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
)

MODEL_FILE = "model.pkl"
METADATA_FILE = "metadata.json"
PINNED_LIBRARIES = ("xgboost", "scikit-learn", "numpy")


@dataclass(frozen=True)
class ProductionModel:
    calibrated: CalibratedModel
    calibration_table: list[CalibrationBin]
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_summary(rows: list[DatasetRow]) -> dict[str, Any]:
    cutoffs = sorted({row.cutoff for row in rows})
    positives = sum(row.target for row in rows)
    return {
        "rows": len(rows),
        "positives": positives,
        "positive_rate": positives / len(rows) if rows else 0.0,
        "cutoffs": len(cutoffs),
        "first_cutoff": cutoffs[0].isoformat() if cutoffs else None,
        "last_cutoff": cutoffs[-1].isoformat() if cutoffs else None,
    }


def train_production_model(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    model_version: str = MODEL_VERSION,
) -> ProductionModel:
    base = fit_xgboost(train_rows, validation_rows)
    calibrated = fit_calibration(base, validation_rows)
    calibration_table = build_calibration_table(
        [row.target for row in validation_rows],
        predict_calibrated(calibrated, validation_rows),
    )
    return ProductionModel(
        calibrated=calibrated,
        calibration_table=calibration_table,
        metadata={
            "model_version": model_version,
            "model": "xgboost + isotonic calibration",
            "calibration_method": CALIBRATION_METHOD,
            "best_iteration": base.best_iteration,
            "config": base.config,
            "train": _split_summary(train_rows),
            "validation": _split_summary(validation_rows),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "libraries": {name: version(name) for name in PINNED_LIBRARIES},
        },
    )


def save_production_model(model: ProductionModel, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / MODEL_FILE).open("wb") as handle:
        pickle.dump((model.calibrated, model.calibration_table), handle)
    (directory / METADATA_FILE).write_text(
        json.dumps(model.metadata, indent=2), encoding="utf-8"
    )
    return directory


def load_production_model(directory: Path) -> ProductionModel:
    metadata_path = directory / METADATA_FILE
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"no trained production model at {directory} -- run "
            "scripts/models/train_production_model.py first"
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    mismatched = {
        name: (trained, version(name))
        for name, trained in metadata.get("libraries", {}).items()
        if trained != version(name)
    }
    if mismatched:
        raise RuntimeError(
            f"production model was trained with different library versions "
            f"(trained, installed): {mismatched}; retrain it"
        )

    with (directory / MODEL_FILE).open("rb") as handle:
        calibrated, calibration_table = pickle.load(handle)  # noqa: S301
    return ProductionModel(calibrated, calibration_table, metadata)
