import json
import time
from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.harness import SUPPORTED_MODELS
from ai_earth_intelligence_and_forecasting_engine.models.profiling import (
    ComputationProfile,
    StageProfile,
    profile_all_models,
    profile_input_files,
    profile_model,
    profile_stage,
    save_computation_profile,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(
    tile_id: str, target: int, previous_24h_count: int, split: str
) -> DatasetRow:
    return DatasetRow(
        tile_id=tile_id,
        cutoff=CUTOFF,
        split=split,
        target=target,
        previous_24h_count=previous_24h_count,
        previous_72h_count=0,
        previous_7d_count=0,
        previous_30d_count=0,
        neighboring_previous_24h_count=0,
        temperature_2m=None,
        total_precipitation=None,
        u_wind_10m=None,
        v_wind_10m=None,
        relative_humidity=None,
        elevation_m=None,
        slope_deg=None,
        land_cover_class=None,
    )


def _separable_split(split: str, offset: int) -> list[DatasetRow]:
    high_targets = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0]
    low_targets = [0, 0, 0, 0, 0, 0, 0, 0, 1, 0]

    rows = [
        _row(f"high-{split}-{offset}-{i}", target, previous_24h_count=50, split=split)
        for i, target in enumerate(high_targets)
    ]
    rows += [
        _row(f"low-{split}-{offset}-{i}", target, previous_24h_count=0, split=split)
        for i, target in enumerate(low_targets)
    ]
    return rows


TRAIN_ROWS = _separable_split("train", 0)
VALIDATION_ROWS = _separable_split("validation", 1)
TEST_ROWS = _separable_split("test", 2)


def test_profile_stage_measures_wall_time_and_returns_the_function_result():
    def slow_fn() -> int:
        time.sleep(0.05)
        return 42

    result, stage = profile_stage("slow", slow_fn)

    assert result == 42
    assert stage.name == "slow"
    assert stage.wall_time_seconds >= 0.04


def test_profile_stage_measures_memory_allocation():
    def allocate_fn() -> list[int]:
        return [0] * 2_000_000

    _result, stage = profile_stage("allocate", allocate_fn)

    assert stage.peak_memory_mb > 1.0


def test_profile_input_files_reports_real_sizes(tmp_path):
    file_a = tmp_path / "a.txt"
    file_a.write_text("x" * 100, encoding="utf-8")
    file_b = tmp_path / "b.txt"
    file_b.write_text("y" * 250, encoding="utf-8")

    profiles = profile_input_files({"a": file_a, "b": file_b})
    by_name = {item.name: item for item in profiles}

    assert by_name["a"].size_bytes == 100
    assert by_name["b"].size_bytes == 250


@pytest.mark.parametrize("model_name", SUPPORTED_MODELS)
def test_profile_model_succeeds_on_separable_real_data(tmp_path, model_name):
    profile = profile_model(
        model_name, TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )

    assert profile.model == model_name
    assert profile.used_synthetic_timing_data is False
    assert profile.error is None
    assert profile.training_time_seconds is not None
    assert profile.training_time_seconds >= 0
    assert profile.inference_time_seconds is not None
    assert profile.inference_time_seconds >= 0
    assert profile.peak_memory_mb is not None
    assert profile.peak_memory_mb >= 0


def test_profile_model_falls_back_to_synthetic_data_when_real_data_cannot_fit(
    tmp_path,
):
    single_class_train = [_row("A", 0, 0, "train"), _row("B", 0, 10, "train")]

    profile = profile_model(
        "xgboost",
        single_class_train,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    assert profile.used_synthetic_timing_data is True
    assert profile.error is not None
    assert "only one class" in profile.error
    assert profile.training_time_seconds is not None
    assert profile.inference_time_seconds is not None
    assert profile.peak_memory_mb is not None


def test_profile_model_climatology_never_needs_the_synthetic_fallback(tmp_path):
    single_class_train = [_row("A", 0, 0, "train"), _row("B", 0, 10, "train")]

    profile = profile_model(
        "climatology",
        single_class_train,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    assert profile.used_synthetic_timing_data is False
    assert profile.error is None


def test_profile_all_models_returns_one_profile_per_supported_model(tmp_path):
    profiles = profile_all_models(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )

    assert [item.model for item in profiles] == list(SUPPORTED_MODELS)


def test_save_computation_profile_writes_deltas_to_disk(tmp_path):
    model_profiles = profile_all_models(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )
    profile = ComputationProfile(
        input_files=profile_input_files({}),
        data_loading=StageProfile("data_loading", 0.1, 1.0),
        feature_construction=StageProfile("feature_construction", 0.2, 2.0),
        row_counts={
            "train": len(TRAIN_ROWS),
            "validation": len(VALIDATION_ROWS),
            "test": len(TEST_ROWS),
        },
        models=model_profiles,
    )

    output_path = save_computation_profile(profile, tmp_path / "profile.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["row_counts"]["train"] == len(TRAIN_ROWS)
    assert payload["data_loading"]["name"] == "data_loading"
    assert len(payload["models"]) == len(SUPPORTED_MODELS)
