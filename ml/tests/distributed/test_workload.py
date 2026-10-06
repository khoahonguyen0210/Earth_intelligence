import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    MODEL_VERSION,
    WORKLOAD_SIZE,
    DistributedWorkload,
    freeze_workload,
)


def test_freeze_workload_returns_the_configured_size_by_default():
    workload = freeze_workload()

    assert workload.workload_size == WORKLOAD_SIZE
    assert len(workload.tile_ids) == WORKLOAD_SIZE


def test_freeze_workload_is_deterministic_across_calls():
    first = freeze_workload()
    second = freeze_workload()

    assert first == second


def test_freeze_workload_tile_ids_match_the_grids_own_deterministic_order():
    workload = freeze_workload(workload_size=10)
    real_first_ten = [cell.tile_id for cell in build_california_grid()[:10]]

    assert list(workload.tile_ids) == real_first_ten


def test_freeze_workload_tile_ids_are_unique():
    workload = freeze_workload()

    assert len(set(workload.tile_ids)) == len(workload.tile_ids)


def test_freeze_workload_records_real_version_identifiers():
    workload = freeze_workload()

    assert workload.model_version == MODEL_VERSION
    assert workload.dataset_version
    assert workload.feature_version
    assert workload.grid_version


def test_freeze_workload_rejects_a_size_larger_than_the_real_grid():
    with pytest.raises(ValueError, match="exceeds"):
        freeze_workload(workload_size=10_000_000)


def test_distributed_workload_is_frozen_and_hashable():
    workload = DistributedWorkload(
        grid_version="v1",
        dataset_version="v1",
        feature_version="v1",
        model_version="calibrated_xgboost_v1",
        tile_ids=("CA_0000_0000",),
    )

    hash(workload)
    with pytest.raises(AttributeError):
        workload.workload_size = 5  # type: ignore[misc]
