import random
from datetime import datetime, timezone

import pytest
from sklearn.calibration import calibration_curve

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    build_calibration_table,
    evaluate_calibration,
    fit_calibration,
    plot_reliability_diagram,
    predict_calibrated,
    save_calibration_table,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    fit_xgboost,
    predict_xgboost,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_build_calibration_table_hand_verified_single_entry_bins():
    y_true = [0, 0, 1, 1, 0, 1]
    y_pred = [0.05, 0.15, 0.25, 0.85, 0.95, 0.55]

    table = build_calibration_table(y_true, y_pred, n_bins=10)

    assert len(table) == 6
    by_bin = {entry.bin_index: entry for entry in table}

    assert by_bin[0].predicted_mean == pytest.approx(0.05)
    assert by_bin[0].observed_frequency == pytest.approx(0.0)
    assert by_bin[0].count == 1

    assert by_bin[9].predicted_mean == pytest.approx(0.95)
    assert by_bin[9].observed_frequency == pytest.approx(0.0)
    assert by_bin[9].count == 1


def test_build_calibration_table_averages_within_a_bin():
    y_true = [0, 1, 1]
    y_pred = [0.42, 0.44, 0.48]

    table = build_calibration_table(y_true, y_pred, n_bins=10)

    assert len(table) == 1
    entry = table[0]
    assert entry.bin_index == 4
    assert entry.count == 3
    assert entry.predicted_mean == pytest.approx((0.42 + 0.44 + 0.48) / 3)
    assert entry.observed_frequency == pytest.approx(2 / 3)


def test_calibration_table_matches_sklearn_calibration_curve():
    rng = random.Random(42)
    y_true = [rng.randint(0, 1) for _ in range(200)]
    y_pred = [rng.random() for _ in range(200)]

    table = build_calibration_table(y_true, y_pred, n_bins=10)

    sklearn_prob_true, sklearn_prob_pred = calibration_curve(
        y_true, y_pred, n_bins=10, strategy="uniform"
    )

    assert [entry.predicted_mean for entry in table] == pytest.approx(
        list(sklearn_prob_pred)
    )
    assert [entry.observed_frequency for entry in table] == pytest.approx(
        list(sklearn_prob_true)
    )


def test_build_calibration_table_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        build_calibration_table([0, 1], [0.5])


def test_save_calibration_table_roundtrip(tmp_path):
    table = build_calibration_table([0, 1], [0.2, 0.8])
    output_path = tmp_path / "calibration_table.csv"

    result = save_calibration_table(table, output_path)
    content = result.read_text(encoding="utf-8")

    assert "bin_index,predicted_mean,observed_frequency,count" in content


def test_plot_reliability_diagram_produces_a_real_image_file(tmp_path):
    table = build_calibration_table([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    output_path = tmp_path / "reliability.png"

    result = plot_reliability_diagram(table, output_path)

    assert result.exists()
    assert result.stat().st_size > 0


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
BASE_RESULT = fit_xgboost(TRAIN_ROWS, VALIDATION_ROWS)


def test_fit_calibration_rejects_single_class_validation():
    single_class_validation = [_row("A", 0, 0, "validation")]

    with pytest.raises(ValueError, match="only one class"):
        fit_calibration(BASE_RESULT, single_class_validation)


def test_fit_calibration_does_not_mutate_the_base_model():
    predictions_before = predict_xgboost(BASE_RESULT, TEST_ROWS)
    fit_calibration(BASE_RESULT, VALIDATION_ROWS)
    predictions_after = predict_xgboost(BASE_RESULT, TEST_ROWS)

    assert predictions_before == predictions_after


def test_calibrated_model_still_discriminates_correctly():
    model = fit_calibration(BASE_RESULT, VALIDATION_ROWS)
    predictions = predict_calibrated(model, TEST_ROWS)

    high_mean = sum(predictions[:10]) / 10
    low_mean = sum(predictions[10:]) / 10

    assert high_mean > low_mean


def test_evaluate_calibration_produces_metrics_and_table():
    _model, predictions, metrics, table = evaluate_calibration(
        BASE_RESULT, VALIDATION_ROWS, TEST_ROWS
    )

    assert len(predictions) == len(TEST_ROWS)
    assert metrics.n_samples == len(TEST_ROWS)
    assert len(table) > 0
    assert sum(entry.count for entry in table) == len(TEST_ROWS)
