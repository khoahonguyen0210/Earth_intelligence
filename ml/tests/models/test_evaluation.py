from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    block_bootstrap,
    persistence_scores,
    spatial_fold,
    tile_indices,
)

CUTOFF = datetime(2024, 8, 1, tzinfo=timezone.utc)


def _row(seven_day: int, thirty_day: int, day: int = 0) -> DatasetRow:
    return DatasetRow(
        tile_id="CA_0001_0002",
        cutoff=CUTOFF,
        split="test",
        target=0,
        previous_24h_count=day,
        previous_72h_count=0,
        previous_7d_count=seven_day,
        previous_30d_count=thirty_day,
        neighboring_previous_24h_count=0,
        temperature_2m=None,
        total_precipitation=None,
        u_wind_10m=None,
        v_wind_10m=None,
        relative_humidity=None,
        elevation_m=None,
        slope_deg=None,
        land_cover_class=None,
    )


def test_persistence_ranks_by_recent_fires_and_breaks_ties_with_the_month():
    rows = [_row(0, 0), _row(2, 0), _row(2, 9), _row(0, 50, day=1)]

    seven_day = persistence_scores(rows, "7d")
    one_day = persistence_scores(rows, "24h")

    assert np.argsort(seven_day).tolist() == [0, 3, 1, 2]
    assert one_day[3] > one_day[2]


def test_bootstrap_brackets_the_point_estimate_and_orders_a_better_model_above():
    rng = np.random.default_rng(0)
    groups = np.repeat(np.arange(20), 200)
    y = (rng.random(len(groups)) < 0.05).astype(int)
    informative = y + rng.normal(0, 0.6, len(y))
    noise = rng.normal(0, 1, len(y))

    metric, difference = block_bootstrap(
        y, {"good": informative, "random": noise}, groups, "random", n_samples=200
    )

    for interval in metric.values():
        assert interval.low <= interval.estimate <= interval.high
    assert metric["good"].estimate > metric["random"].estimate
    assert difference["good"].low > 0
    assert "random" not in difference


def test_bootstrap_is_reproducible_with_its_fixed_seed():
    groups = np.repeat(np.arange(10), 50)
    y = np.tile([1] + [0] * 9, 50)
    scores = {"a": np.linspace(0, 1, len(y)), "b": y.astype(float)}

    first = block_bootstrap(y, scores, groups, "a", n_samples=50)
    second = block_bootstrap(y, scores, groups, "a", n_samples=50)

    assert first == second


def test_tile_indices_parse_latitude_then_longitude():
    assert tile_indices("CA_0421_0583") == (421, 583)


@pytest.mark.parametrize("dlat, dlon", [(0, 1), (1, 0), (1, 1), (1, -1), (0, -1)])
def test_adjacent_blocks_never_share_a_fold(dlat, dlon):
    base = spatial_fold("CA_0050_0050")
    neighbour = spatial_fold(f"CA_{50 + 10 * dlat:04d}_{50 + 10 * dlon:04d}")

    assert base != neighbour


def test_cells_in_the_same_block_share_a_fold():
    assert spatial_fold("CA_0050_0050") == spatial_fold("CA_0059_0051")
