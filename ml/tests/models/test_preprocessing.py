from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    LAND_COVER_CLASSES,
    NUMERIC_FEATURE_COLUMNS,
    extract_targets,
    feature_names,
    fit_preprocessor,
    transform,
)

CUTOFF = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _row(
    tile_id: str,
    target: int,
    previous_24h_count: int = 0,
    elevation_m: float | None = None,
    land_cover_class: int | None = None,
) -> DatasetRow:
    return DatasetRow(
        tile_id=tile_id,
        cutoff=CUTOFF,
        split="train",
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
        elevation_m=elevation_m,
        slope_deg=None,
        land_cover_class=land_cover_class,
    )


def test_fit_preprocessor_rejects_empty_training_set():
    with pytest.raises(ValueError, match="empty"):
        fit_preprocessor([])


def test_fit_preprocessor_statistics_come_from_train_only():
    train_rows = [
        _row("A", 0, previous_24h_count=10),
        _row("B", 1, previous_24h_count=20),
        _row("C", 0, previous_24h_count=30),
    ]

    preprocessor = fit_preprocessor(train_rows)

    index = NUMERIC_FEATURE_COLUMNS.index("previous_24h_count")
    assert preprocessor.imputer.statistics_[index] == pytest.approx(20.0)


def test_missing_value_is_imputed_with_train_median():
    train_rows = [
        _row("A", 0, elevation_m=100.0),
        _row("B", 0, elevation_m=200.0),
        _row("C", 1, elevation_m=None),
        _row("D", 0, elevation_m=400.0),
    ]
    preprocessor = fit_preprocessor(train_rows)

    missing = transform(preprocessor, [_row("E", 0, elevation_m=None)])
    explicit_median = transform(preprocessor, [_row("F", 0, elevation_m=200.0)])

    index = NUMERIC_FEATURE_COLUMNS.index("elevation_m")
    assert missing[0, index] == pytest.approx(explicit_median[0, index])


def test_transform_uses_train_statistics_not_the_input_rows_own_distribution():
    """Closes Task 3.6's deferred leakage check: 'learned preprocessing
    uses training data only'. If transform() incorrectly recomputed
    statistics from whatever rows it was given (instead of always using
    the train-fit preprocessor), a single wildly-different-valued row
    would self-normalize to 0. It must not."""
    train_rows = [
        _row("A", 0, previous_24h_count=0),
        _row("B", 0, previous_24h_count=0),
        _row("C", 1, previous_24h_count=0),
    ]
    preprocessor = fit_preprocessor(train_rows)

    validation_rows = [_row("D", 0, previous_24h_count=1000)]
    transformed = transform(preprocessor, validation_rows)

    index = NUMERIC_FEATURE_COLUMNS.index("previous_24h_count")
    # Train's previous_24h_count is constant (0), so StandardScaler's
    # fallback for zero-variance columns leaves values unscaled: the
    # transformed value should still reflect the raw 1000, not 0.
    assert transformed[0, index] == pytest.approx(1000.0)


def test_land_cover_one_hot_encoding():
    rows = [_row("A", 0, land_cover_class=10), _row("B", 0, land_cover_class=50)]
    preprocessor = fit_preprocessor(rows)

    transformed = transform(preprocessor, rows)
    numeric_width = len(NUMERIC_FEATURE_COLUMNS)
    class_10_index = numeric_width + LAND_COVER_CLASSES.index(10)
    class_50_index = numeric_width + LAND_COVER_CLASSES.index(50)

    assert transformed[0, class_10_index] == 1.0
    assert transformed[0, class_50_index] == 0.0
    assert transformed[1, class_50_index] == 1.0


def test_land_cover_none_produces_all_zero_one_hot():
    train_rows = [_row("A", 0, land_cover_class=10)]
    preprocessor = fit_preprocessor(train_rows)

    transformed = transform(preprocessor, [_row("B", 0, land_cover_class=None)])
    numeric_width = len(NUMERIC_FEATURE_COLUMNS)
    categorical_section = transformed[0, numeric_width:]

    assert categorical_section.sum() == 0.0


def test_extract_targets():
    rows = [_row("A", 1), _row("B", 0)]

    assert extract_targets(rows).tolist() == [1, 0]


def test_all_missing_training_column_does_not_shrink_output_width():
    """A numeric feature that is entirely None across the whole training
    split (e.g. an environmental variable with no real data ingested for
    that period) must still produce a column, not be silently dropped --
    otherwise train/validation/test matrices could end up different
    widths or misaligned."""
    # every optional field is None
    train_rows = [_row("A", 0), _row("B", 1), _row("C", 0)]
    preprocessor = fit_preprocessor(train_rows)

    transformed = transform(preprocessor, train_rows)

    assert transformed.shape[1] == len(feature_names())


def test_feature_names_length_matches_transform_width():
    rows = [_row("A", 0)]
    preprocessor = fit_preprocessor(rows)

    transformed = transform(preprocessor, rows)

    assert transformed.shape[1] == len(feature_names())
