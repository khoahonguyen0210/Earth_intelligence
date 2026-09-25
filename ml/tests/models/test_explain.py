from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
from xgboost import DMatrix

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.explain import (
    Contributions,
    compute_contributions,
    mean_absolute_importance,
    top_drivers,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    transform,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    train_production_model,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(index: int, split: str, target: int, fires: int) -> DatasetRow:
    return DatasetRow(
        tile_id=f"{split}-{index}",
        cutoff=CUTOFF,
        split=split,
        target=target,
        previous_24h_count=fires,
        previous_72h_count=fires,
        previous_7d_count=fires + index % 3,
        previous_30d_count=fires + index % 5,
        neighboring_previous_24h_count=index % 2,
        temperature_2m=280.0 + index % 7,
        total_precipitation=0.001 * (index % 4),
        u_wind_10m=float(index % 3),
        v_wind_10m=-float(index % 2),
        relative_humidity=30.0 + index % 9,
        elevation_m=100.0 * (index % 6),
        slope_deg=float(index % 8),
        land_cover_class=(10, 30, 60)[index % 3],
    )


def _split(split: str) -> list[DatasetRow]:
    rows = []
    for index in range(60):
        burning = index % 3 == 0
        target = 1 if burning and index % 9 != 0 else int(index % 17 == 0)
        rows.append(_row(index, split, target, 40 if burning else 0))
    return rows


@pytest.fixture(scope="module")
def model():
    return train_production_model(_split("train"), _split("validation")).calibrated


def test_contributions_plus_bias_reproduce_the_models_own_margin(model):
    rows = _split("test")
    contributions = compute_contributions(model, rows)

    booster = model.base_result.model.get_booster()
    x = transform(model.base_result.preprocessor, rows)
    best = model.base_result.model.best_iteration
    margin = booster.predict(
        DMatrix(x), output_margin=True, iteration_range=(0, best + 1)
    )
    reconstructed = contributions.values.sum(axis=1) + contributions.bias

    np.testing.assert_allclose(reconstructed, margin, atol=1e-4)
    np.testing.assert_allclose(
        1 / (1 + np.exp(-reconstructed)),
        model.base_result.model.predict_proba(x)[:, 1],
        atol=1e-4,
    )


def test_land_cover_one_hot_columns_collapse_into_one_feature(model):
    contributions = compute_contributions(model, _split("test"))

    assert contributions.features.count("land_cover") == 1
    assert not any(
        name.startswith("land_cover_") for name in contributions.features
    )
    assert len(contributions.features) == 13
    assert contributions.values.shape == (60, 13)


def test_the_feature_that_separates_the_classes_ranks_first(model):
    importance = mean_absolute_importance(compute_contributions(model, _split("test")))

    fire_history = {
        "previous_24h_count",
        "previous_72h_count",
        "previous_7d_count",
        "previous_30d_count",
    }
    assert importance[0].feature in fire_history
    values = [entry.contribution for entry in importance]
    assert values == sorted(values, reverse=True)


def test_top_drivers_are_sorted_by_magnitude_and_skip_zero_contributions():
    features = ("a", "b", "c", "d")
    row = np.array([0.1, -0.9, 0.0, 0.4])

    drivers = top_drivers(features, row, k=3)

    assert [driver.feature for driver in drivers] == ["b", "d", "a"]
    assert drivers[0].contribution == pytest.approx(-0.9)
    single = top_drivers(features, np.array([0.0, 0.0, 0.2, 0.0]))
    assert [driver.feature for driver in single] == ["c"]


def test_importance_of_no_rows_is_empty():
    empty = Contributions(
        features=("a",), values=np.zeros((0, 1)), bias=np.zeros(0)
    )

    assert mean_absolute_importance(empty) == ()
