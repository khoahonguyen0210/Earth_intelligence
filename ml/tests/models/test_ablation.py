from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.ablation import (
    FIRE_HISTORY_FEATURE_COLUMNS,
    FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS,
    GEOGRAPHY_FEATURE_COLUMNS,
    WEATHER_FEATURE_COLUMNS,
    run_geography_ablation,
    run_weather_ablation,
    save_ablation_result,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    NUMERIC_FEATURE_COLUMNS,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(
    tile_id: str,
    target: int,
    split: str,
    previous_24h_count: float,
    temperature_2m: float | None,
) -> DatasetRow:
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
        temperature_2m=temperature_2m,
        total_precipitation=None,
        u_wind_10m=None,
        v_wind_10m=None,
        relative_humidity=None,
        elevation_m=None,
        slope_deg=None,
        land_cover_class=None,
    )


def _rows_for_split(split: str, offset: int) -> list[DatasetRow]:
    """Fire-history (previous_24h_count) is deliberately uninformative --
    it alternates between the two classes the same way for both targets,
    so it carries no separating signal on its own. temperature_2m is
    deliberately a clean, perfect separator. This lets a weather-ablation
    test assert (rather than merely hope) that adding weather measurably
    improves metrics over fire-history alone."""
    positive_counts = [0, 50, 0, 50, 0, 50]
    negative_counts = [0, 50, 0, 50, 0, 50]

    rows = [
        _row(
            f"pos-{split}-{offset}-{i}",
            1,
            split,
            previous_24h_count=count,
            temperature_2m=40.0,
        )
        for i, count in enumerate(positive_counts)
    ]
    rows += [
        _row(
            f"neg-{split}-{offset}-{i}",
            0,
            split,
            previous_24h_count=count,
            temperature_2m=10.0,
        )
        for i, count in enumerate(negative_counts)
    ]
    return rows


TRAIN_ROWS = _rows_for_split("train", 0)
VALIDATION_ROWS = _rows_for_split("validation", 1)
TEST_ROWS = _rows_for_split("test", 2)


def test_feature_groups_do_not_overlap_and_combine_cleanly():
    assert set(FIRE_HISTORY_FEATURE_COLUMNS).isdisjoint(WEATHER_FEATURE_COLUMNS)
    assert set(FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS) == set(
        FIRE_HISTORY_FEATURE_COLUMNS
    ) | set(WEATHER_FEATURE_COLUMNS)


def test_run_weather_ablation_both_variants_succeed_on_separable_data():
    result = run_weather_ablation(TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS)

    assert result.baseline.succeeded
    assert result.candidate.succeeded
    assert result.baseline.metrics is not None
    assert result.candidate.metrics is not None


def test_adding_weather_improves_roc_auc_when_fire_history_alone_cannot_separate():
    result = run_weather_ablation(TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS)

    assert result.baseline.metrics is not None
    assert result.candidate.metrics is not None
    # Fire-history alone carries no real signal in this fixture: it should
    # do no better than chance.
    assert result.baseline.metrics.roc_auc == pytest.approx(0.5, abs=0.05)
    # temperature_2m perfectly separates the classes.
    assert result.candidate.metrics.roc_auc == pytest.approx(1.0, abs=0.01)

    assert result.roc_auc_delta is not None
    assert result.roc_auc_delta > 0.4


def test_ablation_variants_use_the_expected_feature_columns():
    result = run_weather_ablation(TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS)

    assert result.baseline.feature_columns == FIRE_HISTORY_FEATURE_COLUMNS
    assert (
        result.candidate.feature_columns == FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS
    )


def test_run_weather_ablation_handles_single_class_training_gracefully():
    single_class_train = [
        _row("A", 0, "train", previous_24h_count=0, temperature_2m=10.0),
        _row("B", 0, "train", previous_24h_count=50, temperature_2m=40.0),
    ]

    result = run_weather_ablation(single_class_train, VALIDATION_ROWS, TEST_ROWS)

    assert result.baseline.succeeded is False
    assert result.baseline.error is not None
    assert "only one class" in result.baseline.error
    assert result.candidate.succeeded is False
    assert result.pr_auc_delta is None
    assert result.roc_auc_delta is None


def test_save_ablation_result_writes_deltas_to_disk(tmp_path):
    result = run_weather_ablation(TRAIN_ROWS, VALIDATION_ROWS, TEST_ROWS)
    output_path = save_ablation_result(result, tmp_path / "weather_ablation.json")

    import json

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["baseline"]["name"] == "fire_history_only"
    assert payload["candidate"]["name"] == "fire_history_plus_weather"
    assert payload["deltas"]["roc_auc"] == pytest.approx(result.roc_auc_delta)


def _geography_row(
    tile_id: str, target: int, split: str, land_cover_class: int | None
) -> DatasetRow:
    """Fire-history and weather are constant across every row here (no
    signal at all), so the fire-history+weather baseline should do no
    better than chance. land_cover_class cleanly separates the classes,
    so the geography candidate should discriminate near-perfectly."""
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
        temperature_2m=20.0,
        total_precipitation=0.0,
        u_wind_10m=0.0,
        v_wind_10m=0.0,
        relative_humidity=50.0,
        elevation_m=None,
        slope_deg=None,
        land_cover_class=land_cover_class,
    )


def _geography_rows_for_split(split: str, offset: int) -> list[DatasetRow]:
    rows = [
        _geography_row(f"pos-{split}-{offset}-{i}", 1, split, land_cover_class=50)
        for i in range(6)
    ]
    rows += [
        _geography_row(f"neg-{split}-{offset}-{i}", 0, split, land_cover_class=10)
        for i in range(6)
    ]
    return rows


GEO_TRAIN_ROWS = _geography_rows_for_split("train", 0)
GEO_VALIDATION_ROWS = _geography_rows_for_split("validation", 1)
GEO_TEST_ROWS = _geography_rows_for_split("test", 2)


def test_geography_feature_columns_combine_with_fire_history_and_weather():
    combined = (
        FIRE_HISTORY_FEATURE_COLUMNS
        + WEATHER_FEATURE_COLUMNS
        + GEOGRAPHY_FEATURE_COLUMNS
    )
    assert combined == NUMERIC_FEATURE_COLUMNS


def test_run_geography_ablation_both_variants_succeed_on_separable_data():
    result = run_geography_ablation(GEO_TRAIN_ROWS, GEO_VALIDATION_ROWS, GEO_TEST_ROWS)

    assert result.baseline.succeeded
    assert result.candidate.succeeded
    assert result.baseline.include_land_cover is False
    assert result.candidate.include_land_cover is True


def test_adding_geography_improves_roc_auc_when_weather_alone_cannot_separate():
    result = run_geography_ablation(GEO_TRAIN_ROWS, GEO_VALIDATION_ROWS, GEO_TEST_ROWS)

    assert result.baseline.metrics is not None
    assert result.candidate.metrics is not None
    # fire-history+weather carries no signal in this fixture.
    assert result.baseline.metrics.roc_auc == pytest.approx(0.5, abs=0.05)
    # land_cover_class perfectly separates the classes.
    assert result.candidate.metrics.roc_auc == pytest.approx(1.0, abs=0.01)

    assert result.roc_auc_delta is not None
    assert result.roc_auc_delta > 0.4


def test_geography_ablation_variants_use_the_expected_feature_columns():
    result = run_geography_ablation(GEO_TRAIN_ROWS, GEO_VALIDATION_ROWS, GEO_TEST_ROWS)

    assert result.baseline.feature_columns == FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS
    assert result.candidate.feature_columns == NUMERIC_FEATURE_COLUMNS


def test_run_geography_ablation_handles_single_class_training_gracefully():
    single_class_train = [
        _geography_row("A", 0, "train", land_cover_class=10),
        _geography_row("B", 0, "train", land_cover_class=50),
    ]

    result = run_geography_ablation(
        single_class_train, GEO_VALIDATION_ROWS, GEO_TEST_ROWS
    )

    assert result.baseline.succeeded is False
    assert result.baseline.error is not None
    assert "only one class" in result.baseline.error
    assert result.candidate.succeeded is False
    assert result.roc_auc_delta is None
