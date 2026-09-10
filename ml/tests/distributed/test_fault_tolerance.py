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

# Small on purpose -- see test_run.py's own comment. The fault-injection
# run against the full 500-tile workload lives in
# scripts/distributed/run_fault_injection_test.py.
SMALL_WORKLOAD_SIZE = 4


@pytest.fixture(scope="module")
def context():
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
    # Four checks against a real killed worker: process_chunk really calls
    # os._exit for the injected chunk -- confirmed live that
    # Pool.apply_async's result then times out, never raises a distinct
    # exception.
    #
    # task_timeout_seconds=30, not a tight bound: Pool replaces the dead
    # worker with a brand-new process, which must pay the same real
    # spawn+import cold-start cost (multiple real seconds, measured
    # separately) before it can even start the retried task -- a shorter
    # timeout was observed live to mistake that legitimate cold start for
    # a second crash and trigger an extra, unnecessary retry.
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    result = run_with_fault_tolerance(
        workload,
        num_workers=2,
        context=context,
        task_timeout_seconds=30,
        max_retries=2,
        inject_crash_in_chunk=0,
    )

    # [x] failure detected
    assert result.any_failure_detected is True
    crashed_outcome = result.chunk_outcomes[0]
    assert crashed_outcome.failure_detected is True

    # [x] task retried when appropriate
    assert crashed_outcome.attempts >= 2

    # [x] no final result lost
    assert result.all_chunks_eventually_succeeded is True
    assert result.total_tiles == SMALL_WORKLOAD_SIZE
    for outcome in result.chunk_outcomes:
        assert outcome.result is not None

    # [x] terminal state correct, and a real recovery time was recorded
    assert crashed_outcome.recovery_seconds is not None
    assert crashed_outcome.recovery_seconds >= 0

    # The other (non-crashed) chunk's own result is untouched by the
    # crash -- it never needed a retry at all.
    surviving_outcome = result.chunk_outcomes[1]
    assert surviving_outcome.failure_detected is False
    assert surviving_outcome.attempts == 1


def test_a_chunk_that_exhausts_retries_is_reported_as_failed_not_silently_dropped(
    context,
):
    # A worker that crashes on every single attempt (inject_crash never
    # cleared -- simulated here via 0 retries, so the very first crash
    # already exhausts the budget) must show up as a real recorded
    # failure with no result, not vanish from the final report.
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
    # The surviving chunk's real result must still be reported, even
    # though its sibling failed -- one chunk's terminal failure must not
    # lose or hide another chunk's real, already-obtained result.
    assert result.chunk_outcomes[1].result is not None
