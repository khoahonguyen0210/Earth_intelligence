import json
import math

import pytest

from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    compute_metrics,
    metrics_to_dict,
    save_metrics,
)

Y_TRUE = [0, 0, 1, 1]
Y_PRED = [0.1, 0.4, 0.35, 0.8]


def test_roc_auc_matches_known_reference_value():
    metrics = compute_metrics(Y_TRUE, Y_PRED)

    assert metrics.roc_auc == pytest.approx(0.75)


def test_brier_score_matches_hand_computed_mean_squared_error():
    expected = ((0 - 0.1) ** 2 + (0 - 0.4) ** 2 + (1 - 0.35) ** 2 + (1 - 0.8) ** 2) / 4

    metrics = compute_metrics(Y_TRUE, Y_PRED)

    assert metrics.brier_score == pytest.approx(expected)


def test_log_loss_matches_independently_computed_formula():
    expected = -sum(
        y * math.log(p) + (1 - y) * math.log(1 - p) for y, p in zip(Y_TRUE, Y_PRED)
    ) / len(Y_TRUE)

    metrics = compute_metrics(Y_TRUE, Y_PRED)

    assert metrics.log_loss == pytest.approx(expected)


def test_positive_rate_and_counts():
    metrics = compute_metrics(Y_TRUE, Y_PRED)

    assert metrics.n_samples == 4
    assert metrics.n_positive == 2
    assert metrics.positive_rate == 0.5


def test_single_class_produces_nan_auc_not_a_crash():
    metrics = compute_metrics([0, 0, 0], [0.1, 0.2, 0.05])

    assert math.isnan(metrics.pr_auc)
    assert math.isnan(metrics.roc_auc)
    assert metrics.brier_score >= 0
    assert metrics.log_loss >= 0


def test_all_positive_class_produces_nan_auc_not_a_crash():
    metrics = compute_metrics([1, 1, 1], [0.9, 0.8, 0.95])

    assert math.isnan(metrics.pr_auc)
    assert math.isnan(metrics.roc_auc)


def test_extreme_predictions_do_not_produce_infinite_log_loss():
    metrics = compute_metrics([1, 0], [0.0, 1.0])

    assert math.isfinite(metrics.log_loss)


def test_compute_metrics_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        compute_metrics([0, 1], [0.5])


def test_compute_metrics_rejects_empty_input():
    with pytest.raises(ValueError, match="empty"):
        compute_metrics([], [])


def test_metrics_to_dict_is_json_serializable():
    metrics = compute_metrics(Y_TRUE, Y_PRED)
    payload = metrics_to_dict(metrics)

    json.dumps(payload)

    assert payload["n_samples"] == 4


def test_save_metrics_roundtrip(tmp_path):
    metrics = compute_metrics(Y_TRUE, Y_PRED)
    output_path = tmp_path / "metrics.json"

    result = save_metrics(metrics, output_path)
    saved = json.loads(result.read_text(encoding="utf-8"))

    assert saved["roc_auc"] == pytest.approx(0.75)
