import dataclasses
from pathlib import Path

import pytest

from ai_earth_intelligence_and_forecasting_engine.distributed.run import (
    DistributedRunResult,
    RunContext,
    chunk_tile_ids,
    fit_baseline_model,
    prepare_run_context,
    run_distributed_inference,
)
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    DistributedWorkload,
    freeze_workload,
)
from ai_earth_intelligence_and_forecasting_engine.models.profiling import (
    synthetic_timing_rows,
)

RAW_FIRMS_PATH = Path("data/raw/firms/firms_sample.csv")
RAW_ERA5_PATH = Path("data/raw/era5/era5_sample.nc")
GEOGRAPHY_BBOX = (-119.8, 37.2, -119.4, 37.6)
DEM_PATH = Path("data/raw/geography/dem_sample.tif")
LANDCOVER_PATH = Path("data/raw/geography/landcover_sample.tif")

# Small on purpose: these tests exercise the real pipeline (real sample
# data, a real XGBoost fit, real multiprocessing) end to end, not a fast
# mock -- kept tiny (well under the full 500-tile frozen workload) so the
# suite stays fast. The real baseline number comes from
# scripts/distributed/run_baseline.py against the full frozen workload.
SMALL_WORKLOAD_SIZE = 6


def _small_workload() -> DistributedWorkload:
    return freeze_workload(workload_size=SMALL_WORKLOAD_SIZE)


@pytest.fixture(scope="module")
def context() -> RunContext:
    # module-scoped: real data loading + a real model fit is expensive
    # enough that every test in this file should share one, exercising
    # the same RunContext-reuse property the distributed run itself
    # relies on.
    return prepare_run_context(
        raw_firms_path=RAW_FIRMS_PATH,
        raw_era5_path=RAW_ERA5_PATH,
        geography_bbox=GEOGRAPHY_BBOX,
        dem_path=DEM_PATH,
        landcover_path=LANDCOVER_PATH,
    )


@pytest.mark.parametrize(
    "num_workers,expected_chunks", [(1, [3]), (2, [2, 1]), (4, [1, 1, 1])]
)
def test_chunk_tile_ids_splits_into_near_equal_contiguous_chunks(
    num_workers, expected_chunks
):
    tile_ids = ("a", "b", "c")

    chunks = chunk_tile_ids(tile_ids, num_workers)

    assert [len(chunk) for chunk in chunks] == expected_chunks
    assert tuple(tile_id for chunk in chunks for tile_id in chunk) == tile_ids


def test_chunk_tile_ids_never_returns_an_empty_chunk_with_more_workers_than_tiles():
    chunks = chunk_tile_ids(("a", "b"), num_workers=5)

    assert len(chunks) == 2
    assert all(len(chunk) > 0 for chunk in chunks)


def test_chunk_tile_ids_rejects_fewer_than_one_worker():
    with pytest.raises(ValueError, match="num_workers"):
        chunk_tile_ids(("a",), num_workers=0)


def _all_single_class(rows, target: int):
    return [dataclasses.replace(row, target=target) for row in rows]


def test_fit_baseline_model_falls_back_on_the_known_single_class_gap():
    # The real demo cutoffs' rows have zero real positive labels (every
    # label is 0) -- this must not raise, it must fall back, and say so.
    single_class_train = _all_single_class(
        synthetic_timing_rows(20, "train"), target=0
    )
    single_class_validation = _all_single_class(
        synthetic_timing_rows(20, "validation"), target=0
    )

    model, used_fallback = fit_baseline_model(
        single_class_train, single_class_validation
    )

    assert used_fallback is True
    assert model is not None


def test_run_distributed_inference_with_one_worker_processes_every_tile(context):
    workload = _small_workload()

    result = run_distributed_inference(workload, num_workers=1, context=context)

    assert isinstance(result, DistributedRunResult)
    assert result.actual_workers == 1
    assert result.workload_size == SMALL_WORKLOAD_SIZE
    assert result.wall_seconds > 0
    assert result.throughput_tiles_per_second > 0
    assert result.total_cpu_seconds >= 0
    assert result.peak_memory_mb > 0


def test_run_distributed_inference_with_multiple_workers_processes_every_tile(context):
    workload = _small_workload()

    result = run_distributed_inference(workload, num_workers=2, context=context)

    assert result.actual_workers == 2
    assert result.workload_size == SMALL_WORKLOAD_SIZE


def test_run_distributed_inference_uses_fewer_workers_than_requested_if_needed(context):
    workload = freeze_workload(workload_size=2)

    result = run_distributed_inference(workload, num_workers=8, context=context)

    assert result.requested_workers == 8
    assert result.actual_workers == 2
    assert result.workload_size == 2


def test_run_distributed_inference_does_not_mutate_the_shared_context(context):
    # The same prepared RunContext (data + fitted model) must back every
    # worker-count run in a sweep unchanged -- a second call must not
    # have altered it.
    workload = _small_workload()
    model_before = context.model

    run_distributed_inference(workload, num_workers=1, context=context)

    assert context.model is model_before
    assert context.used_synthetic_model_fallback is True
