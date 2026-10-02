from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("torch")

from sklearn.metrics import average_precision_score  # noqa: E402

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (  # noqa: E402
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.research.neural import (  # noqa: E402
    build_network,
    fit_neural,
    predict_neural,
)

CUTOFF = datetime(2020, 8, 1, tzinfo=timezone.utc)


def _rows(split: str, n: int = 600) -> list[DatasetRow]:
    rows = []
    for index in range(n):
        burning = index % 7 == 0
        rows.append(
            DatasetRow(
                tile_id=f"{split}-{index}",
                cutoff=CUTOFF,
                split=split,
                target=1 if burning and index % 3 else 0,
                previous_24h_count=5 if burning else 0,
                previous_72h_count=0,
                previous_7d_count=8 if burning else index % 2,
                previous_30d_count=index % 4,
                neighboring_previous_24h_count=0,
                temperature_2m=290.0 + index % 5,
                total_precipitation=0.0,
                u_wind_10m=0.0,
                v_wind_10m=0.0,
                relative_humidity=40.0,
                elevation_m=float(index % 9) * 100,
                slope_deg=5.0,
                land_cover_class=(10, 30)[index % 2],
            )
        )
    return rows


def test_network_maps_features_to_one_logit():
    network = build_network(23)

    assert network[-1].out_features == 1
    assert network[0].in_features == 23


def test_learns_a_separable_signal_and_ranks_fires_first():
    result = fit_neural(_rows("train"), _rows("validation"), max_epochs=15)
    test_rows = _rows("test")

    scores = predict_neural(result, test_rows)

    pr_auc = average_precision_score([row.target for row in test_rows], scores)
    assert pr_auc > 0.6
    assert result.best_epoch >= 1
    assert result.validation_pr_auc == max(
        entry["validation_pr_auc"] for entry in result.history
    )


def test_training_is_reproducible_with_the_fixed_seed():
    first = predict_neural(
        fit_neural(_rows("train"), _rows("validation"), max_epochs=3), _rows("test")
    )
    second = predict_neural(
        fit_neural(_rows("train"), _rows("validation"), max_epochs=3), _rows("test")
    )

    assert first == pytest.approx(second)


def test_a_split_without_fires_is_refused():
    no_fires = [row for row in _rows("validation") if row.target == 0]

    with pytest.raises(ValueError, match="positive rows"):
        fit_neural(_rows("train"), no_fires)
