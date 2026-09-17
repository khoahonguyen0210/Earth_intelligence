from pathlib import Path

import pytest

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.scaling import (
    run_scaling_benchmark,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    freeze_workload,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

SMALL_WORKLOAD_SIZE = 8


@pytest.fixture(scope="module")
def context():
    return prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )


def test_run_scaling_benchmark_returns_one_point_per_worker_count(context):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    points = run_scaling_benchmark(workload, context, worker_counts=(1, 2, 4))

    assert [point.result.requested_workers for point in points] == [1, 2, 4]


def test_run_scaling_benchmark_the_baseline_point_has_speedup_and_efficiency_of_one(
    context,
):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    points = run_scaling_benchmark(workload, context, worker_counts=(1, 2))

    baseline = points[0]
    assert baseline.result.requested_workers == 1
    assert baseline.speedup == pytest.approx(1.0)
    assert baseline.efficiency == pytest.approx(1.0)


def test_run_scaling_benchmark_efficiency_is_speedup_divided_by_worker_count(context):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    points = run_scaling_benchmark(workload, context, worker_counts=(1, 2, 4))

    for point in points:
        assert point.efficiency == pytest.approx(
            point.speedup / point.result.requested_workers
        )


def test_run_scaling_benchmark_every_point_processes_the_full_workload(context):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    points = run_scaling_benchmark(workload, context, worker_counts=(1, 2, 4))

    for point in points:
        assert point.result.workload_size == SMALL_WORKLOAD_SIZE


def test_run_scaling_benchmark_rejects_an_empty_worker_count_list(context):
    workload = freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)

    with pytest.raises(ValueError, match="worker_counts"):
        run_scaling_benchmark(workload, context, worker_counts=())
