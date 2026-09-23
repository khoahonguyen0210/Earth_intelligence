"""The production model's save/load/metadata contract.

These tests cover its save/load roundtrip, its metadata contents, and
its version-mismatch guard directly, plus one property nothing else
checks: retraining on identical inputs with the module's own fixed
random_state produces identical predictions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import version

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    PINNED_LIBRARIES,
    load_production_model,
    save_production_model,
    train_production_model,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    BASE_CONFIG,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)
LATER_CUTOFF = datetime(2020, 1, 8, tzinfo=timezone.utc)


def _row(
    tile_id: str, target: int, previous_24h_count: int, split: str, cutoff: datetime
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


def _separable_split(split: str, offset: int, cutoff: datetime) -> list[DatasetRow]:
    high_targets = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0]
    low_targets = [0, 0, 0, 0, 0, 0, 0, 0, 1, 0]

    rows = [
        _row(f"high-{split}-{offset}-{i}", target, 50, split, cutoff)
        for i, target in enumerate(high_targets)
    ]
    rows += [
        _row(f"low-{split}-{offset}-{i}", target, 0, split, cutoff)
        for i, target in enumerate(low_targets)
    ]
    return rows


TRAIN_ROWS = _separable_split("train", 0, CUTOFF) + _separable_split(
    "train", 1, LATER_CUTOFF
)
VALIDATION_ROWS = _separable_split("validation", 2, LATER_CUTOFF)
TEST_ROWS = _separable_split("test", 3, LATER_CUTOFF)


# --- metadata contents -------------------------------------------------


def test_train_production_model_metadata_has_every_reproducibility_field():
    model = train_production_model(TRAIN_ROWS, VALIDATION_ROWS)

    assert model.metadata["model_version"]
    assert model.metadata["calibration_method"]
    assert isinstance(model.metadata["best_iteration"], int)
    assert model.metadata["trained_at"]
    # Never a placeholder -- the fixed seed this model's config actually used.
    assert model.metadata["config"]["random_state"] == BASE_CONFIG["random_state"]
    assert model.metadata["libraries"].keys() == set(PINNED_LIBRARIES)
    for name in PINNED_LIBRARIES:
        assert model.metadata["libraries"][name] == version(name)


def test_train_production_model_split_summaries_match_the_real_rows():
    model = train_production_model(TRAIN_ROWS, VALIDATION_ROWS)

    train_summary = model.metadata["train"]
    assert train_summary["rows"] == len(TRAIN_ROWS)
    assert train_summary["positives"] == sum(row.target for row in TRAIN_ROWS)
    assert train_summary["positive_rate"] == pytest.approx(
        train_summary["positives"] / train_summary["rows"]
    )
    assert train_summary["cutoffs"] == 2
    assert train_summary["first_cutoff"] == CUTOFF.isoformat()
    assert train_summary["last_cutoff"] == LATER_CUTOFF.isoformat()

    validation_summary = model.metadata["validation"]
    assert validation_summary["rows"] == len(VALIDATION_ROWS)
    assert validation_summary["cutoffs"] == 1
    assert validation_summary["first_cutoff"] == LATER_CUTOFF.isoformat()


# --- save/load roundtrip ------------------------------------------------


def test_save_and_load_production_model_roundtrips_predictions(tmp_path):
    model = train_production_model(TRAIN_ROWS, VALIDATION_ROWS)
    predictions_before = predict_calibrated(model.calibrated, TEST_ROWS)

    save_production_model(model, tmp_path)
    loaded = load_production_model(tmp_path)
    predictions_after = predict_calibrated(loaded.calibrated, TEST_ROWS)

    assert predictions_after == predictions_before
    assert loaded.calibration_table == model.calibration_table
    assert loaded.metadata == model.metadata


def test_load_production_model_missing_metadata_raises_with_the_retrain_hint(tmp_path):
    with pytest.raises(FileNotFoundError, match="train_production_model.py"):
        load_production_model(tmp_path)


def test_load_production_model_refuses_a_library_version_mismatch(tmp_path):
    model = train_production_model(TRAIN_ROWS, VALIDATION_ROWS)
    save_production_model(model, tmp_path)

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace(
            version("numpy"), "0.0.0-not-installed"
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="different library versions"):
        load_production_model(tmp_path)


# --- reproducibility: the fixed seed actually reproduces ---------------


def test_retraining_on_identical_inputs_with_the_fixed_seed_reproduces_predictions():
    first = train_production_model(TRAIN_ROWS, VALIDATION_ROWS)
    second = train_production_model(TRAIN_ROWS, VALIDATION_ROWS)

    assert predict_calibrated(first.calibrated, TEST_ROWS) == predict_calibrated(
        second.calibrated, TEST_ROWS
    )
    assert first.calibration_table == second.calibration_table
    assert first.metadata["best_iteration"] == second.metadata["best_iteration"]
