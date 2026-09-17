from pathlib import Path

import pytest

from ai_earth_intelligence_and_forecasting_engine.distributed.bottleneck import (
    build_sample_chunk_task,
    identify_bottleneck,
    measure_serialization_cost,
    measure_spawn_overhead,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    prepare_run_context,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")


@pytest.fixture(scope="module")
def context():
    return prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )


def test_measure_spawn_overhead_returns_a_non_negative_real_measurement():
    overhead = measure_spawn_overhead(num_workers=2)

    assert overhead.num_workers == 2
    assert overhead.wall_seconds >= 0


def test_measure_spawn_overhead_rejects_fewer_than_one_worker():
    with pytest.raises(ValueError, match="num_workers"):
        measure_spawn_overhead(num_workers=0)


def test_measure_serialization_cost_on_a_real_chunk_task(context):
    task = build_sample_chunk_task(context, next(iter(context.cells_by_id)))

    cost = measure_serialization_cost(task)

    assert cost.pickle_seconds >= 0
    assert cost.unpickle_seconds >= 0
    assert cost.payload_bytes > 0


def test_identify_bottleneck_never_names_network_or_database(context):
    report = identify_bottleneck(
        context, worker_counts=(1, 2), real_compute_seconds=0.001
    )

    assert report.dominant_factor not in {"network", "database"}


def test_identify_bottleneck_names_coordination_when_spawn_overhead_dominates(
    context,
):
    report = identify_bottleneck(
        context, worker_counts=(1, 8), real_compute_seconds=0.0001
    )

    assert report.dominant_factor == "coordination"
    assert "coordination" in report.reasoning


def test_identify_bottleneck_names_cpu_when_compute_dominates(context):
    report = identify_bottleneck(
        context, worker_counts=(1,), real_compute_seconds=10_000.0
    )

    assert report.dominant_factor == "cpu"


def test_identify_bottleneck_records_every_worker_counts_measurement(context):
    report = identify_bottleneck(
        context, worker_counts=(1, 2, 4), real_compute_seconds=0.001
    )

    assert [overhead.num_workers for overhead in report.spawn_overhead] == [1, 2, 4]
