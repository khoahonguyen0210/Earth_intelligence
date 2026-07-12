from datetime import date

from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    FORECAST_WINDOW_HOURS,
    TEST_SPLIT,
    TRAIN_SPLIT,
    VALIDATION_SPLIT,
    split_for_date,
)


def test_forecast_window_is_24_hours():
    assert FORECAST_WINDOW_HOURS == 24


def test_split_ranges_are_locked():
    assert TRAIN_SPLIT.start == date(2019, 1, 1)
    assert TRAIN_SPLIT.end == date(2022, 12, 31)
    assert VALIDATION_SPLIT.start == date(2023, 1, 1)
    assert VALIDATION_SPLIT.end == date(2023, 12, 31)
    assert TEST_SPLIT.start == date(2024, 1, 1)
    assert TEST_SPLIT.end == date(2024, 12, 31)


def test_split_ranges_do_not_overlap():
    assert TRAIN_SPLIT.end < VALIDATION_SPLIT.start
    assert VALIDATION_SPLIT.end < TEST_SPLIT.start


def test_split_for_date_train_boundaries():
    assert split_for_date(date(2019, 1, 1)) == "train"
    assert split_for_date(date(2022, 12, 31)) == "train"


def test_split_for_date_validation_boundaries():
    assert split_for_date(date(2023, 1, 1)) == "validation"
    assert split_for_date(date(2023, 12, 31)) == "validation"


def test_split_for_date_test_boundaries():
    assert split_for_date(date(2024, 1, 1)) == "test"
    assert split_for_date(date(2024, 12, 31)) == "test"


def test_split_for_date_outside_all_splits_returns_none():
    assert split_for_date(date(2018, 12, 31)) is None
    assert split_for_date(date(2025, 1, 1)) is None


def test_split_for_date_train_validation_gap_is_exact():
    assert split_for_date(date(2022, 12, 31)) == "train"
    assert split_for_date(date(2023, 1, 1)) == "validation"


def test_split_for_date_validation_test_gap_is_exact():
    assert split_for_date(date(2023, 12, 31)) == "validation"
    assert split_for_date(date(2024, 1, 1)) == "test"
