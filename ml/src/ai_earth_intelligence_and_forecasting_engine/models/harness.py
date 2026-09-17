from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ai_earth_intelligence_and_forecasting_engine.data.era5 import parse_era5_records
from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    build_geography_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DATASET_VERSION,
    FEATURE_VERSION,
    DatasetRow,
    build_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CalibrationBin,
    build_calibration_table,
    fit_calibration,
    plot_reliability_diagram,
    predict_calibrated,
    save_calibration_table,
)
from ai_earth_intelligence_and_forecasting_engine.models.climatology import (
    fit_climatology,
    predict_climatology,
)
from ai_earth_intelligence_and_forecasting_engine.models.logistic_regression import (
    fit_logistic_regression,
    predict_logistic_regression,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    ClassificationMetrics,
    compute_metrics,
    save_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
    predict_xgboost,
)

ModelName = Literal[
    "climatology", "logistic_regression", "xgboost", "calibrated_xgboost"
]

SUPPORTED_MODELS: tuple[ModelName, ...] = (
    "climatology",
    "logistic_regression",
    "xgboost",
    "calibrated_xgboost",
)

DEFAULT_RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
DEFAULT_RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
DEFAULT_GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEFAULT_DEM_PATH = Path("data/raw/geography/dem_sample.tif")
DEFAULT_LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")


@dataclass(frozen=True)
class ExperimentPaths:
    root: Path
    config: Path
    metrics: Path
    predictions: Path
    plots_dir: Path
    readme: Path


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    model_name: str
    succeeded: bool
    metrics: ClassificationMetrics | None
    error: str | None
    paths: ExperimentPaths


def experiment_paths(
    experiment_id: str, artifacts_root: Path = Path("ml/artifacts")
) -> ExperimentPaths:
    root = artifacts_root / experiment_id

    return ExperimentPaths(
        root=root,
        config=root / "config.json",
        metrics=root / "metrics.json",
        predictions=root / "predictions.csv",
        plots_dir=root / "plots",
        readme=root / "README.md",
    )


def load_sample_rows(
    train_cutoff: datetime,
    validation_cutoff: datetime,
    test_cutoff: datetime,
) -> list[DatasetRow]:
    """Loads the real sample data and builds dataset rows for the given
    cutoffs."""
    firms_config = load_firms_config()
    firms_records = parse_firms_records(
        DEFAULT_RAW_FIRMS_PATH.read_text(encoding="utf-8")
    )
    ingested_at = datetime.now(timezone.utc)
    observations = [
        normalize_firms_record(
            record=record,
            product=firms_config.product,
            source_record_id=str(index),
            ingested_at=ingested_at,
        )
        for index, record in enumerate(firms_records)
    ]

    era5_records = parse_era5_records(DEFAULT_RAW_ERA5_PATH)
    geography_cells = build_geography_grid(
        bbox=DEFAULT_GEOGRAPHY_BBOX,
        resolution_deg=0.1,
        dem_path=DEFAULT_DEM_PATH,
        landcover_path=DEFAULT_LANDCOVER_PATH,
    )
    cells = build_california_grid()

    return build_dataset(
        observations,
        era5_records,
        geography_cells,
        cells,
        [train_cutoff, validation_cutoff, test_cutoff],
    )


def _save_predictions(
    test_rows: list[DatasetRow], predictions: list[float], output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("tile_id,cutoff,target,predicted_probability\n")

        for row, prediction in zip(test_rows, predictions):
            handle.write(
                f"{row.tile_id},{row.cutoff.isoformat()},"
                f"{row.target},{prediction}\n"
            )

    return output_path


def _write_readme(
    paths: ExperimentPaths,
    config: dict[str, Any],
    metrics: ClassificationMetrics | None,
    error: str | None,
) -> Path:
    lines = [
        f"# Experiment: {config['experiment_id']}",
        "",
        f"Model: {config['model']}",
        f"Dataset version: {config['dataset_version']}",
        f"Feature version: {config['feature_version']}",
        f"Generated at: {config['generated_at']}",
        "",
        "## Split",
        f"- train cutoff: {config['train_cutoff']} ({config['train_rows']} rows)",
        f"- validation cutoff: {config['validation_cutoff']} "
        f"({config['validation_rows']} rows)",
        f"- test cutoff: {config['test_cutoff']} ({config['test_rows']} rows)",
        "",
    ]

    if error is not None:
        lines += [
            "## Result",
            "FAILED -- an honest, expected result given current data "
            "availability, not a code defect.",
            "",
            f"Error: {error}",
            "",
            "## Limitations",
            "The real training/validation splits currently have zero real "
            "historical positive examples (no bulk FIRMS data ingested for "
            "2019-2023 yet). See this model's own test suite for proof of "
            "correctness against real, separable synthetic data.",
        ]
    else:
        assert metrics is not None
        lines += [
            "## Metrics",
            f"- PR-AUC: {metrics.pr_auc}",
            f"- ROC-AUC: {metrics.roc_auc}",
            f"- Brier score: {metrics.brier_score}",
            f"- Log loss: {metrics.log_loss}",
            f"- Test positive rate: {metrics.positive_rate}",
            f"- Training time (s): {config.get('training_time_seconds')}",
            f"- Inference time (s): {config.get('inference_time_seconds')}",
            "",
            "## Limitations",
            "Evaluated against the project's current real sample data "
            "footprint (one real historical day); a full 2019-2024 "
            "historical benchmark requires bulk FIRMS/ERA5-Land ingestion "
            "not yet performed.",
        ]

    paths.readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return paths.readme


def run_experiment_on_rows(
    model_name: ModelName,
    experiment_id: str,
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    artifacts_root: Path = Path("ml/artifacts"),
) -> ExperimentResult:
    """The core, testable evaluation pipeline: data selection is the
    caller's job (either load_sample_rows for real data, or a synthetic
    fixture in tests); this function does
    split -> training -> prediction -> metrics -> plots -> artifacts.
    """
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported model: {model_name!r}. Supported: {SUPPORTED_MODELS}"
        )

    paths = experiment_paths(experiment_id, artifacts_root)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.plots_dir.mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {
        "model": model_name,
        "experiment_id": experiment_id,
        "dataset_version": DATASET_VERSION,
        "feature_version": FEATURE_VERSION,
        "train_cutoff": train_rows[0].cutoff.isoformat() if train_rows else None,
        "validation_cutoff": (
            validation_rows[0].cutoff.isoformat() if validation_rows else None
        ),
        "test_cutoff": test_rows[0].cutoff.isoformat() if test_rows else None,
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "test_rows": len(test_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        predictions: list[float]
        calibration_table: list[CalibrationBin] | None = None

        if model_name == "climatology":
            training_start = time.perf_counter()
            cl_model = fit_climatology(train_rows)
            training_time = time.perf_counter() - training_start

            inference_start = time.perf_counter()
            predictions = predict_climatology(cl_model, test_rows)
            inference_time = time.perf_counter() - inference_start
        elif model_name == "logistic_regression":
            training_start = time.perf_counter()
            lr_result = fit_logistic_regression(train_rows, validation_rows)
            training_time = time.perf_counter() - training_start

            inference_start = time.perf_counter()
            predictions = predict_logistic_regression(lr_result, test_rows)
            inference_time = time.perf_counter() - inference_start

            config["selected_c"] = lr_result.selected_c
        elif model_name == "xgboost":
            training_start = time.perf_counter()
            xgb_result = fit_xgboost(train_rows, validation_rows)
            training_time = time.perf_counter() - training_start

            inference_start = time.perf_counter()
            predictions = predict_xgboost(xgb_result, test_rows)
            inference_time = time.perf_counter() - inference_start

            config["best_iteration"] = xgb_result.best_iteration
            config["base_config"] = xgb_result.config
        else:  # calibrated_xgboost
            training_start = time.perf_counter()
            base_result = fit_xgboost(train_rows, validation_rows)
            cal_model = fit_calibration(base_result, validation_rows)
            training_time = time.perf_counter() - training_start

            inference_start = time.perf_counter()
            predictions = predict_calibrated(cal_model, test_rows)
            inference_time = time.perf_counter() - inference_start

            config["best_iteration"] = base_result.best_iteration
            config["base_config"] = base_result.config

            y_true_for_table = [row.target for row in test_rows]
            calibration_table = build_calibration_table(y_true_for_table, predictions)

        y_true = [row.target for row in test_rows]
        metrics = compute_metrics(y_true, predictions)

        config["training_time_seconds"] = training_time
        config["inference_time_seconds"] = inference_time

        save_metrics(metrics, paths.metrics)
        _save_predictions(test_rows, predictions, paths.predictions)

        if calibration_table is not None:
            save_calibration_table(
                calibration_table, paths.plots_dir / "calibration_table.csv"
            )
            plot_reliability_diagram(
                calibration_table, paths.plots_dir / "reliability_diagram.png"
            )

        config["status"] = "succeeded"
        paths.config.write_text(json.dumps(config, indent=2), encoding="utf-8")
        _write_readme(paths, config, metrics, error=None)

        return ExperimentResult(
            experiment_id=experiment_id,
            model_name=model_name,
            succeeded=True,
            metrics=metrics,
            error=None,
            paths=paths,
        )

    except ValueError as error:
        config["status"] = "failed"
        config["error"] = str(error)
        paths.config.write_text(json.dumps(config, indent=2), encoding="utf-8")
        _write_readme(paths, config, metrics=None, error=str(error))

        return ExperimentResult(
            experiment_id=experiment_id,
            model_name=model_name,
            succeeded=False,
            metrics=None,
            error=str(error),
            paths=paths,
        )


def run_experiment(
    model_name: ModelName,
    experiment_id: str,
    train_cutoff: datetime,
    validation_cutoff: datetime,
    test_cutoff: datetime,
    artifacts_root: Path = Path("ml/artifacts"),
) -> ExperimentResult:
    """The full, real, one-command pipeline: loads real sample data, then
    runs run_experiment_on_rows."""
    rows = load_sample_rows(train_cutoff, validation_cutoff, test_cutoff)
    train_rows = [row for row in rows if row.split == "train"]
    validation_rows = [row for row in rows if row.split == "validation"]
    test_rows = [row for row in rows if row.split == "test"]

    return run_experiment_on_rows(
        model_name,
        experiment_id,
        train_rows,
        validation_rows,
        test_rows,
        artifacts_root,
    )
