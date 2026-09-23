from pathlib import Path

import pytest

from ai_earth_intelligence_and_forecasting_engine.distributed.fault_tolerance import (
    run_with_fault_tolerance,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    freeze_workload,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

SMALL_WORKLOAD_SIZE = 4


@pytest.fixture(scope="module")
def context():
    if not RAW_FIRMS_PATH.exists() or not RAW_ERA5_PATH.exists():
        pytest.skip("real raw sample data not downloaded")
    return prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )


def test_a_run_with_no_injected_crash_succeeds_on_the_first_attempt(context):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    result = run_with_fault_tolerance(
        workload,
        num_workers=2,
        context=context,
        task_timeout_seconds=30,
        max_retries=2,
        inject_crash_in_chunk=None,
    )

    assert result.any_failure_detected is False
    assert result.all_chunks_eventually_succeeded is True
    assert result.total_tiles == SMALL_WORKLOAD_SIZE
    assert all(outcome.attempts == 1 for outcome in result.chunk_outcomes)


def test_a_killed_worker_is_detected_retried_and_recovers_with_no_result_lost(context):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    result = run_with_fault_tolerance(
        workload,
        num_workers=2,
        context=context,
        task_timeout_seconds=30,
        max_retries=2,
        inject_crash_in_chunk=0,
    )

    assert result.any_failure_detected is True
    crashed_outcome = result.chunk_outcomes[0]
    assert crashed_outcome.failure_detected is True

    assert crashed_outcome.attempts >= 2

    assert result.all_chunks_eventually_succeeded is True
    assert result.total_tiles == SMALL_WORKLOAD_SIZE
    for outcome in result.chunk_outcomes:
        assert outcome.result is not None

    assert crashed_outcome.recovery_seconds is not None
    assert crashed_outcome.recovery_seconds >= 0

    surviving_outcome = result.chunk_outcomes[1]
    assert surviving_outcome.failure_detected is False
    assert surviving_outcome.attempts == 1


def test_a_chunk_that_exhausts_retries_is_reported_as_failed_not_silently_dropped(
    context,
):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    result = run_with_fault_tolerance(
        workload,
        num_workers=2,
        context=context,
        task_timeout_seconds=30,
        max_retries=0,
        inject_crash_in_chunk=0,
    )

    assert result.all_chunks_eventually_succeeded is False
    failed_outcome = result.chunk_outcomes[0]
    assert failed_outcome.result is None
    assert failed_outcome.failure_detected is True
    assert result.chunk_outcomes[1].result is not None
