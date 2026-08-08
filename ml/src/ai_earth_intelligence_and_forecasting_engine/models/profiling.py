from __future__ import annotations

import json
import time
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.harness import (
    SUPPORTED_MODELS,
    ModelName,
    run_experiment_on_rows,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    LAND_COVER_CLASSES,
)

COMPUTATION_PROFILE_VERSION = "v1"

T = TypeVar("T")


@dataclass(frozen=True)
class StageProfile:
    name: str
    wall_time_seconds: float
    peak_memory_mb: float


@dataclass(frozen=True)
class InputFileProfile:
    name: str
    path: str
    size_bytes: int


@dataclass(frozen=True)
class ModelProfile:
    model: str
    training_time_seconds: float | None
    inference_time_seconds: float | None
    peak_memory_mb: float | None
    used_synthetic_timing_data: bool
    error: str | None


@dataclass(frozen=True)
class ComputationProfile:
    input_files: list[InputFileProfile]
    data_loading: StageProfile
    feature_construction: StageProfile
    row_counts: dict[str, int]
    models: list[ModelProfile]


def profile_stage(name: str, fn: Callable[[], T]) -> tuple[T, StageProfile]:
    """Measures wall time and Python-level peak memory (via tracemalloc)
    for one pipeline stage. tracemalloc tracks Python object allocations;
    it under-counts memory a native extension (numpy/xgboost) allocates
    outside the Python allocator, so peak_memory_mb is a lower bound on
    true process memory, not an exact RSS figure."""
    tracemalloc.start()
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return result, StageProfile(
        name=name, wall_time_seconds=elapsed, peak_memory_mb=peak / (1024 * 1024)
    )


def profile_input_files(paths: dict[str, Path]) -> list[InputFileProfile]:
    return [
        InputFileProfile(name=name, path=str(path), size_bytes=path.stat().st_size)
        for name, path in paths.items()
    ]


def synthetic_timing_rows(n: int, split: str) -> list[DatasetRow]:
    """Realistically-shaped, deterministic rows used only to measure
    training/inference wall-time and memory when the real split cannot
    support a fit (see harness.py's documented single-class data gap:
    the real train/validation splits currently have zero real historical
    positive examples). Both classes are present by construction. These
    rows are never used to compute or report an accuracy metric -- only
    computational cost, which depends on data volume and shape, not on
    whether the labels are scientifically real."""
    rng = np.random.default_rng(20240815)
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)

    return [
        DatasetRow(
            tile_id=f"synthetic-{split}-{i}",
            cutoff=cutoff,
            split=split,
            target=i % 2,
            previous_24h_count=int(rng.integers(0, 10)),
            previous_72h_count=int(rng.integers(0, 20)),
            previous_7d_count=int(rng.integers(0, 40)),
            previous_30d_count=int(rng.integers(0, 100)),
            neighboring_previous_24h_count=int(rng.integers(0, 10)),
            temperature_2m=float(rng.uniform(260, 320)),
            total_precipitation=float(rng.uniform(0, 0.02)),
            u_wind_10m=float(rng.uniform(-10, 10)),
            v_wind_10m=float(rng.uniform(-10, 10)),
            relative_humidity=float(rng.uniform(5, 100)),
            elevation_m=float(rng.uniform(0, 3000)),
            slope_deg=float(rng.uniform(0, 45)),
            land_cover_class=int(rng.choice(LAND_COVER_CLASSES)),
        )
        for i in range(n)
    ]


def _load_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


def _run_and_measure_memory(
    model_name: ModelName,
    experiment_id: str,
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    artifacts_root: Path,
) -> tuple[bool, str | None, Path | None, float]:
    tracemalloc.start()
    result = run_experiment_on_rows(
        model_name,
        experiment_id,
        train_rows,
        validation_rows,
        test_rows,
        artifacts_root,
    )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    config_path = result.paths.config if result.succeeded else None
    return result.succeeded, result.error, config_path, peak / (1024 * 1024)


def profile_model(
    model_name: ModelName,
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    artifacts_root: Path = Path("ml/artifacts"),
    experiment_prefix: str = "computation_profile_v1",
) -> ModelProfile:
    """Task 5.4: training/inference time and memory for one model. Reuses
    harness.py's already-tested fit/predict dispatch and timing capture
    entirely -- this function only adds memory measurement and, when the
    real split cannot support a fit, a synthetic-shaped-data fallback so
    computational cost can still be measured (see synthetic_timing_rows
    for why that is not the same thing as fabricating an accuracy
    result)."""
    succeeded, error, config_path, peak_memory_mb = _run_and_measure_memory(
        model_name,
        f"{experiment_prefix}_{model_name}",
        train_rows,
        validation_rows,
        test_rows,
        artifacts_root,
    )

    if succeeded:
        assert config_path is not None
        config = _load_config(config_path)
        return ModelProfile(
            model=model_name,
            training_time_seconds=config["training_time_seconds"],
            inference_time_seconds=config["inference_time_seconds"],
            peak_memory_mb=peak_memory_mb,
            used_synthetic_timing_data=False,
            error=None,
        )

    real_error = error
    (
        synthetic_succeeded,
        synthetic_error,
        synthetic_config_path,
        synthetic_peak_memory_mb,
    ) = _run_and_measure_memory(
        model_name,
        f"{experiment_prefix}_{model_name}_synthetic_timing",
        synthetic_timing_rows(max(len(train_rows), 2), "train"),
        synthetic_timing_rows(max(len(validation_rows), 2), "validation"),
        synthetic_timing_rows(max(len(test_rows), 2), "test"),
        artifacts_root,
    )

    if not synthetic_succeeded:
        return ModelProfile(
            model=model_name,
            training_time_seconds=None,
            inference_time_seconds=None,
            peak_memory_mb=None,
            used_synthetic_timing_data=True,
            error=(
                f"{real_error} (synthetic timing fallback also failed: "
                f"{synthetic_error})"
            ),
        )

    assert synthetic_config_path is not None
    synthetic_config = _load_config(synthetic_config_path)

    return ModelProfile(
        model=model_name,
        training_time_seconds=synthetic_config["training_time_seconds"],
        inference_time_seconds=synthetic_config["inference_time_seconds"],
        peak_memory_mb=synthetic_peak_memory_mb,
        used_synthetic_timing_data=True,
        error=real_error,
    )


def profile_all_models(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    artifacts_root: Path = Path("ml/artifacts"),
    experiment_prefix: str = "computation_profile_v1",
) -> list[ModelProfile]:
    return [
        profile_model(
            model_name,
            train_rows,
            validation_rows,
            test_rows,
            artifacts_root,
            experiment_prefix,
        )
        for model_name in SUPPORTED_MODELS
    ]


def save_computation_profile(profile: ComputationProfile, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "computation_profile_version": COMPUTATION_PROFILE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_files": [asdict(item) for item in profile.input_files],
        "data_loading": asdict(profile.data_loading),
        "feature_construction": asdict(profile.feature_construction),
        "row_counts": profile.row_counts,
        "models": [asdict(item) for item in profile.models],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return output_path
