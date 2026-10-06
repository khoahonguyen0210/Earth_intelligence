from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.harness import (
    experiment_paths,
    run_experiment_on_rows,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(
    tile_id: str, target: int, previous_24h_count: int, split: str, cutoff=CUTOFF
) -> DatasetRow:
    return DatasetRow(
        tile_id=tile_id,
        cutoff=cutoff,
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


def test_experiment_paths_structure(tmp_path):
    paths = experiment_paths("my_experiment", artifacts_root=tmp_path)

    assert paths.root == tmp_path / "my_experiment"
    assert paths.config.name == "config.json"
    assert paths.metrics.name == "metrics.json"
    assert paths.predictions.name == "predictions.csv"
    assert paths.plots_dir.name == "plots"
    assert paths.readme.name == "README.md"


def test_run_experiment_on_rows_rejects_unsupported_model(tmp_path):
    with pytest.raises(ValueError, match="Unsupported model"):
        run_experiment_on_rows(
            "not_a_real_model",  # type: ignore[arg-type]
            "bad",
            TRAIN_ROWS,
            VALIDATION_ROWS,
            TEST_ROWS,
            artifacts_root=tmp_path,
        )


@pytest.mark.parametrize(
    "model_name",
    ["climatology", "logistic_regression", "xgboost", "calibrated_xgboost"],
)
def test_run_experiment_on_rows_succeeds_and_writes_all_artifacts(tmp_path, model_name):
    result = run_experiment_on_rows(
        model_name,
        f"{model_name}_experiment",
        TRAIN_ROWS,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    assert result.succeeded
    assert result.metrics is not None
    assert result.error is None

    assert result.paths.config.exists()
    assert result.paths.metrics.exists()
    assert result.paths.predictions.exists()
    assert result.paths.readme.exists()

    predictions_content = result.paths.predictions.read_text(encoding="utf-8")
    assert predictions_content.count("\n") == len(TEST_ROWS) + 1

    readme_content = result.paths.readme.read_text(encoding="utf-8")
    assert model_name in readme_content
    assert "Metrics" in readme_content


def test_run_experiment_on_rows_calibrated_xgboost_saves_plots(tmp_path):
    result = run_experiment_on_rows(
        "calibrated_xgboost",
        "calibrated_experiment",
        TRAIN_ROWS,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    assert result.succeeded
    assert (result.paths.plots_dir / "calibration_table.csv").exists()
    assert (result.paths.plots_dir / "reliability_diagram.png").exists()


def test_run_experiment_on_rows_handles_single_class_training_gracefully(tmp_path):
    single_class_train = [_row("A", 0, 0, "train"), _row("B", 0, 10, "train")]

    result = run_experiment_on_rows(
        "xgboost",
        "failing_experiment",
        single_class_train,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    assert result.succeeded is False
    assert result.metrics is None
    assert result.error is not None
    assert "only one class" in result.error

    assert result.paths.config.exists()
    assert result.paths.readme.exists()
    assert not result.paths.metrics.exists()

    readme_content = result.paths.readme.read_text(encoding="utf-8")
    assert "FAILED" in readme_content
    assert "only one class" in readme_content


@pytest.mark.parametrize(
    "model_name",
    ["climatology", "logistic_regression", "xgboost", "calibrated_xgboost"],
)
def test_run_experiment_on_rows_records_training_and_inference_time(
    tmp_path, model_name
):
    result = run_experiment_on_rows(
        model_name,
        f"{model_name}_timing",
        TRAIN_ROWS,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    import json

    config = json.loads(result.paths.config.read_text(encoding="utf-8"))

    assert config["training_time_seconds"] >= 0
    assert config["inference_time_seconds"] >= 0

    readme_content = result.paths.readme.read_text(encoding="utf-8")
    assert "Training time" in readme_content
    assert "Inference time" in readme_content


def test_run_experiment_on_rows_config_records_split_sizes(tmp_path):
    result = run_experiment_on_rows(
        "climatology",
        "config_check",
        TRAIN_ROWS,
        VALIDATION_ROWS,
        TEST_ROWS,
        artifacts_root=tmp_path,
    )

    import json

    config = json.loads(result.paths.config.read_text(encoding="utf-8"))

    assert config["train_rows"] == len(TRAIN_ROWS)
    assert config["validation_rows"] == len(VALIDATION_ROWS)
    assert config["test_rows"] == len(TEST_ROWS)
    assert config["status"] == "succeeded"
