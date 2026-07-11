import pytest

from ai_earth_intelligence_and_forecasting_engine.query.regression_set import (
    REGRESSION_CASES,
    check_regression_case,
)

SAMPLE_CSV = (
    "latitude,longitude,acq_date,acq_time,confidence\n"
    "37.8,-122.4,2024-08-01,1000,n\n"  # Bay Area
    "34.0,-118.2,2024-08-01,1400,h\n"  # Southern California
    "37.5,-119.5,2024-08-08,0900,n\n"  # generic California, different week
    "0.0,0.0,2024-08-01,1000,n\n"  # outside California, excluded everywhere
)


@pytest.fixture
def firms_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "test-key")

    path = tmp_path / "firms_sample.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")

    return path


def test_regression_set_has_at_least_one_case_per_operation():
    operations = {case.expected_operation for case in REGRESSION_CASES}

    assert operations == {"count", "daily_aggregate", "weekly_aggregate", "map"}


def test_regression_set_has_at_least_one_case_per_region_kind():
    region_kinds = {case.expected_region_kind for case in REGRESSION_CASES}

    assert region_kinds == {"named", "bbox", "coordinates"}


def test_regression_case_names_are_unique():
    names = [case.name for case in REGRESSION_CASES]

    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    "case", REGRESSION_CASES, ids=[case.name for case in REGRESSION_CASES]
)
def test_regression_case_passes(case, firms_csv):
    passed, errors, _response = check_regression_case(case, firms_csv)

    assert passed, f"{case.name} failed: {errors}"
