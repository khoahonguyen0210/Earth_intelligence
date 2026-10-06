from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    BASE_CONFIG,
    evaluate_xgboost,
    fit_xgboost,
    predict_xgboost,
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


def test_fit_xgboost_rejects_single_class_training_data():
    single_class_rows = [_row("A", 0, 0, "train"), _row("B", 0, 10, "train")]

    with pytest.raises(ValueError, match="only one class"):
        fit_xgboost(single_class_rows, VALIDATION_ROWS)


def test_fit_xgboost_rejects_single_class_validation_data():
    single_class_validation = [_row("A", 0, 0, "validation")]

    with pytest.raises(ValueError, match="Early stopping needs both classes"):
        fit_xgboost(TRAIN_ROWS, single_class_validation)


def test_fit_xgboost_uses_early_stopping_to_pick_fewer_trees_than_the_cap():
    result = fit_xgboost(TRAIN_ROWS, VALIDATION_ROWS)

    assert 0 <= result.best_iteration < BASE_CONFIG["n_estimators"] - 1


def test_fit_xgboost_preserves_the_fixed_base_config():
    result = fit_xgboost(TRAIN_ROWS, VALIDATION_ROWS)

    assert result.config["max_depth"] == BASE_CONFIG["max_depth"]
    assert result.config["learning_rate"] == BASE_CONFIG["learning_rate"]
    assert result.config["objective"] == "binary:logistic"


def test_model_learns_the_correct_direction_of_the_signal():
    result = fit_xgboost(TRAIN_ROWS, VALIDATION_ROWS)

    predictions = predict_xgboost(result, TEST_ROWS)
    high_count_predictions = predictions[:10]
    low_count_predictions = predictions[10:]

    assert min(high_count_predictions) > max(low_count_predictions)


def test_evaluate_xgboost_does_not_use_test_targets_to_select_config():
    result_a, _predictions_a, _metrics_a = evaluate_xgboost(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS
    )
    reversed_test_rows = list(reversed(TEST_ROWS))
    result_b, _predictions_b, _metrics_b = evaluate_xgboost(
        TRAIN_ROWS, VALIDATION_ROWS, reversed_test_rows
    )

    assert result_a.best_iteration == result_b.best_iteration


def test_evaluate_xgboost_produces_locked_metrics():
    _result, _predictions, metrics = evaluate_xgboost(
        TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS
    )

    assert metrics.n_samples == len(TEST_ROWS)
    assert 0.0 <= metrics.roc_auc <= 1.0
    assert metrics.roc_auc > 0.7
