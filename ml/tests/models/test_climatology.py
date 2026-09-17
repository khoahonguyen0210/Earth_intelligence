from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.climatology import (
    evaluate_climatology,
    fit_climatology,
    predict_climatology,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(tile_id: str, target: int, split: str = "train") -> DatasetRow:
    return DatasetRow(
        tile_id=tile_id,
        cutoff=CUTOFF,
        split=split,
        target=target,
        previous_24h_count=0,
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


TRAIN_ROWS = (
    [_row("tile-A", 1) for _ in range(3)]
    + [_row("tile-A", 0)]
    + [_row("tile-B", 1)]
    + [_row("tile-B", 0) for _ in range(4)]
    + [_row("tile-C", 0) for _ in range(2)]
)


def test_fit_climatology_computes_exact_per_tile_rates():
    model = fit_climatology(TRAIN_ROWS)

    assert model.tile_rates["tile-A"] == pytest.approx(0.75)
    assert model.tile_rates["tile-B"] == pytest.approx(0.2)
    assert model.tile_rates["tile-C"] == pytest.approx(0.0)


def test_fit_climatology_computes_exact_global_rate():
    model = fit_climatology(TRAIN_ROWS)

    assert model.global_rate == pytest.approx(4 / 11)


def test_fit_climatology_rejects_empty_training_set():
    with pytest.raises(ValueError, match="empty"):
        fit_climatology([])


def test_predict_climatology_uses_the_tiles_own_rate():
    model = fit_climatology(TRAIN_ROWS)
    test_rows = [_row("tile-A", 1, split="test"), _row("tile-B", 0, split="test")]

    predictions = predict_climatology(model, test_rows)

    assert predictions == [pytest.approx(0.75), pytest.approx(0.2)]


def test_predict_climatology_falls_back_to_global_rate_for_unseen_tile():
    model = fit_climatology(TRAIN_ROWS)
    test_rows = [_row("tile-never-seen", 0, split="test")]

    predictions = predict_climatology(model, test_rows)

    assert predictions == [pytest.approx(4 / 11)]


def test_evaluate_climatology_never_uses_test_rows_to_fit():
    test_rows = [_row("tile-D", 1, split="test"), _row("tile-D", 0, split="test")]

    model, predictions, _metrics = evaluate_climatology(TRAIN_ROWS, test_rows)

    assert "tile-D" not in model.tile_rates
    assert predictions == [pytest.approx(4 / 11), pytest.approx(4 / 11)]


def test_evaluate_climatology_metrics_reflect_test_targets():
    test_rows = [
        _row("tile-A", 1, split="test"),
        _row("tile-B", 0, split="test"),
    ]

    _model, _predictions, metrics = evaluate_climatology(TRAIN_ROWS, test_rows)

    assert metrics.n_samples == 2
    assert metrics.n_positive == 1
    assert metrics.positive_rate == pytest.approx(0.5)
