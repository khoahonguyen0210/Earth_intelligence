from datetime import datetime, timedelta, timezone

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    fire_history_features as fhf,
)

CUTOFF = datetime(2024, 8, 15, 12, 0, tzinfo=timezone.utc)
TEST_BBOX = (-120.0, 37.0, -119.7, 37.3)
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)
CENTER_TILE = "CA_0001_0001"


def _obs(
    observation_id: str,
    when: datetime,
    latitude: float = 37.15,
    longitude: float = -119.85,
    confidence: str | None = "n",
) -> Observation:
    return Observation(
        observation_id=observation_id,
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=when,
        latitude=latitude,
        longitude=longitude,
        source_record_id=observation_id,
        ingested_at=datetime(2024, 8, 16, tzinfo=timezone.utc),
        confidence=confidence,
    )


def _features(observations, cells=CELLS, cutoffs=(CUTOFF,), bbox=TEST_BBOX):
    return fhf.compute_fire_history_features(
        observations, cells, list(cutoffs), bbox=bbox
    )


def _center(records):
    return next(r for r in records if r.tile_id == CENTER_TILE)


def test_previous_24h_count_only_counts_within_24h():
    inside = _obs("in", CUTOFF - timedelta(hours=23))
    outside = _obs("out", CUTOFF - timedelta(hours=25))

    record = _center(_features([inside, outside]))

    assert record.previous_24h_count == 1


def test_previous_72h_count_window():
    inside = _obs("in", CUTOFF - timedelta(hours=71))
    outside = _obs("out", CUTOFF - timedelta(hours=73))

    record = _center(_features([inside, outside]))

    assert record.previous_72h_count == 1


def test_previous_7d_count_window():
    inside = _obs("in", CUTOFF - timedelta(days=6, hours=23))
    outside = _obs("out", CUTOFF - timedelta(days=7, hours=1))

    record = _center(_features([inside, outside]))

    assert record.previous_7d_count == 1


def test_previous_30d_count_window():
    inside = _obs("in", CUTOFF - timedelta(days=29, hours=23))
    outside = _obs("out", CUTOFF - timedelta(days=30, hours=1))

    record = _center(_features([inside, outside]))

    assert record.previous_30d_count == 1


def test_observation_exactly_at_cutoff_is_included():
    observation = _obs("at-cutoff", CUTOFF)

    record = _center(_features([observation]))

    assert record.previous_24h_count == 1
    assert record.previous_72h_count == 1
    assert record.previous_7d_count == 1
    assert record.previous_30d_count == 1


def test_observation_one_second_before_window_start_is_excluded():
    observation = _obs("just-outside", CUTOFF - timedelta(hours=24, seconds=1))

    record = _center(_features([observation]))

    assert record.previous_24h_count == 0
    assert record.previous_72h_count == 1


def test_future_observations_do_not_alter_features():
    past_observation = _obs("past", CUTOFF - timedelta(hours=1))

    without_future = _features([past_observation])

    future_observation = _obs("future", CUTOFF + timedelta(hours=1))
    with_future = _features([past_observation, future_observation])

    assert without_future == with_future


def test_future_observation_alone_produces_all_zero_features():
    future_observation = _obs("future", CUTOFF + timedelta(seconds=1))

    record = _center(_features([future_observation]))

    assert record.previous_24h_count == 0
    assert record.previous_72h_count == 0
    assert record.previous_7d_count == 0
    assert record.previous_30d_count == 0
    assert record.neighboring_previous_24h_count == 0


def test_neighboring_previous_24h_count_includes_adjacent_cell():
    neighbor_observation = _obs(
        "neighbor", CUTOFF - timedelta(hours=1), latitude=37.15, longitude=-119.75
    )

    record = _center(_features([neighbor_observation]))

    assert record.previous_24h_count == 0
    assert record.neighboring_previous_24h_count == 1


def test_neighboring_previous_24h_count_excludes_the_cell_itself():
    own_observation = _obs("own", CUTOFF - timedelta(hours=1))

    record = _center(_features([own_observation]))

    assert record.previous_24h_count == 1
    assert record.neighboring_previous_24h_count == 0


def test_neighboring_count_respects_the_24h_window_not_longer_ones():
    old_neighbor_observation = _obs(
        "old-neighbor",
        CUTOFF - timedelta(hours=48),
        latitude=37.15,
        longitude=-119.75,
    )

    record = _center(_features([old_neighbor_observation]))

    assert record.neighboring_previous_24h_count == 0


def test_compute_fire_history_features_one_record_per_cell_per_cutoff():
    cutoffs = [CUTOFF, CUTOFF + timedelta(hours=1)]

    records = _features([], cutoffs=cutoffs)

    assert len(records) == len(CELLS) * len(cutoffs)
    pairs = {(r.tile_id, r.cutoff) for r in records}
    assert len(pairs) == len(CELLS) * len(cutoffs)


def test_save_fire_history_features_roundtrip(tmp_path):
    records = _features([])

    output_path = tmp_path / "features.csv"
    result = fhf.save_fire_history_features(records, output_path)

    content = result.read_text(encoding="utf-8")

    assert "previous_24h_count" in content
    assert "neighboring_previous_24h_count" in content
    assert CENTER_TILE in content
