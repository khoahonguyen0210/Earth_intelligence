import json
from datetime import datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.benchmark import (
    run_baseline_benchmark,
    save_benchmark_comparison,
    save_benchmark_table,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(tile_id: str, target: int, previous_24h_count: int, split: str) -> DatasetRow:
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


def test_run_baseline_benchmark_covers_all_four_locked_models(tmp_path):
    rows = run_baseline_benchmark(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )

    assert {row.model for row in rows} == {
        "climatology",
        "logistic_regression",
        "xgboost",
        "calibrated_xgboost",
    }


def test_run_baseline_benchmark_all_models_succeed_on_separable_data(tmp_path):
    rows = run_baseline_benchmark(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )

    assert all(row.succeeded for row in rows)
    assert all(row.pr_auc is not None for row in rows)
    assert all(row.roc_auc is not None for row in rows)


def test_run_baseline_benchmark_records_positive_training_and_inference_time(
    tmp_path,
):
    rows = run_baseline_benchmark(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )

    for row in rows:
        assert row.training_time_seconds is not None
        assert row.training_time_seconds >= 0
        assert row.inference_time_seconds is not None
        assert row.inference_time_seconds >= 0


def test_run_baseline_benchmark_reports_failure_honestly(tmp_path):
    """Single-class training data (matching this project's real current
    data footprint) makes logistic_regression/xgboost/calibrated_xgboost
    honestly fail -- but climatology has no such requirement (it just
    computes an empirical rate, well-defined even for one class), so it
    genuinely succeeds. This exact split mirrors what actually happens
    against the project's real sample data (see the Task 4.1-4.5 demo
    scripts)."""
    single_class_train = [_row("A", 0, 0, "train"), _row("B", 0, 10, "train")]

    rows = run_baseline_benchmark(
        single_class_train, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )
    by_model = {row.model: row for row in rows}

    assert by_model["climatology"].succeeded is True
    assert by_model["climatology"].error is None

    for model_name in ("logistic_regression", "xgboost", "calibrated_xgboost"):
        assert by_model[model_name].succeeded is False
        assert by_model[model_name].error is not None
        assert by_model[model_name].pr_auc is None


def test_save_benchmark_comparison_roundtrip(tmp_path):
    rows = run_baseline_benchmark(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )
    output_path = tmp_path / "comparison.json"

    save_benchmark_comparison(rows, output_path)
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(saved["models"]) == 4
    assert "benchmark_version" in saved


def test_save_benchmark_table_roundtrip(tmp_path):
    rows = run_baseline_benchmark(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS, artifacts_root=tmp_path
    )
    output_path = tmp_path / "comparison.csv"

    result = save_benchmark_table(rows, output_path)
    content = result.read_text(encoding="utf-8")

    assert "model,succeeded,pr_auc,roc_auc" in content
    assert "climatology" in content
    assert "calibrated_xgboost" in content
