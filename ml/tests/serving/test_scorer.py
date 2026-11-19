from __future__ import annotations

import numpy as np
import pytest
import xgboost

from ai_earth_intelligence_and_forecasting_engine.serving.scorer import (
    PortableScorer,
)


@pytest.fixture
def portable_model():
    generator = np.random.default_rng(4)
    features = generator.normal(size=(400, 5)).astype(np.float32)
    labels = (features[:, 0] + 0.5 * features[:, 1] > 0).astype(int)
    booster = xgboost.train(
        {"max_depth": 3, "objective": "binary:logistic", "nthread": 1},
        xgboost.DMatrix(features, label=labels),
        num_boost_round=12,
    )
    model = {
        "format_version": 1,
        "best_iteration": 7,
        "booster": bytes(booster.save_raw("json")).decode("utf-8"),
        "isotonic_x": [0.0, 0.5, 1.0],
        "isotonic_y": [0.0, 0.2, 1.0],
    }
    return model, booster, features


def test_scores_use_the_best_trees_and_the_calibration(portable_model):
    model, booster, features = portable_model
    scorer = PortableScorer(model, "cpu", threads=1)
    raw = booster.predict(xgboost.DMatrix(features), iteration_range=(0, 8))
    np.testing.assert_allclose(scorer.raw(features), raw, rtol=0, atol=1e-7)
    np.testing.assert_allclose(
        scorer(features), np.interp(raw, [0.0, 0.5, 1.0], [0.0, 0.2, 1.0]), atol=1e-7
    )


def test_unknown_formats_are_rejected(portable_model):
    model, _, _ = portable_model
    with pytest.raises(ValueError):
        PortableScorer({**model, "format_version": 2})


def test_the_scorer_reads_the_exported_format():
    from ai_earth_intelligence_and_forecasting_engine.earth2 import portable
    from ai_earth_intelligence_and_forecasting_engine.serving import scorer

    assert scorer.FORMAT_VERSION == portable.FORMAT_VERSION
