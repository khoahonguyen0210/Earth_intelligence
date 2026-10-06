from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast.labels import (
    construct_labels,
    hourly_cutoffs,
    is_qualifying_observation,
    save_labels,
)

CUTOFF = datetime(2024, 8, 15, 0, 0, tzinfo=timezone.utc)
TEST_BBOX = (-120.0, 37.5, -119.9, 37.6)
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)


def _labels(observations, cells, cutoffs, bbox=TEST_BBOX):
    return construct_labels(observations, cells, cutoffs, bbox=bbox)


def _obs(
    observation_id: str,
    when: datetime,
    latitude: float = 37.55,
    longitude: float = -119.95,
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


def test_is_qualifying_observation_accepts_nominal_and_high_confidence():
    assert is_qualifying_observation(_obs("1", CUTOFF, confidence="n")) is True
    assert is_qualifying_observation(_obs("2", CUTOFF, confidence="h")) is True


def test_is_qualifying_observation_rejects_low_confidence():
    assert is_qualifying_observation(_obs("1", CUTOFF, confidence="l")) is False
    assert is_qualifying_observation(_obs("1", CUTOFF, confidence="L")) is False


def test_is_qualifying_observation_accepts_missing_confidence():
    assert is_qualifying_observation(_obs("1", CUTOFF, confidence=None)) is True


def test_is_qualifying_observation_rejects_invalid_coordinates():
    assert is_qualifying_observation(_obs("1", CUTOFF, latitude=91.0)) is False
    assert is_qualifying_observation(_obs("1", CUTOFF, longitude=-200.0)) is False


def test_is_qualifying_observation_rejects_naive_timestamp():
    naive_observation = replace(
        _obs("1", CUTOFF), observed_at=datetime(2024, 8, 15)
    )

    assert is_qualifying_observation(naive_observation) is False


def test_hourly_cutoffs_generates_expected_sequence():
    start = datetime(2024, 8, 15, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 8, 15, 3, 0, tzinfo=timezone.utc)

    cutoffs = hourly_cutoffs(start, end)

    assert cutoffs == [
        datetime(2024, 8, 15, 0, 0, tzinfo=timezone.utc),
        datetime(2024, 8, 15, 1, 0, tzinfo=timezone.utc),
        datetime(2024, 8, 15, 2, 0, tzinfo=timezone.utc),
    ]


def test_hourly_cutoffs_rejects_naive_datetimes():
    with pytest.raises(ValueError, match="timezone-aware"):
        hourly_cutoffs(
            datetime(2024, 8, 15), datetime(2024, 8, 16, tzinfo=timezone.utc)
        )


def test_construct_labels_positive_example():
    observation = _obs("fire-1", CUTOFF + timedelta(hours=5))

    records = _labels([observation], CELLS, [CUTOFF])

    assert len(records) == 1
    assert records[0].target == 1
    assert records[0].qualifying_observation_ids == ("fire-1",)


def test_construct_labels_negative_example_no_observations():
    records = _labels([], CELLS, [CUTOFF])

    assert len(records) == 1
    assert records[0].target == 0
    assert records[0].qualifying_observation_ids == ()


def test_construct_labels_excludes_observation_exactly_at_cutoff():
    observation = _obs("fire-1", CUTOFF)

    records = _labels([observation], CELLS, [CUTOFF])

    assert records[0].target == 0


def test_construct_labels_includes_observation_exactly_at_window_end():
    observation = _obs("fire-1", CUTOFF + timedelta(hours=24))

    records = _labels([observation], CELLS, [CUTOFF])

    assert records[0].target == 1
    assert records[0].qualifying_observation_ids == ("fire-1",)


def test_construct_labels_excludes_observation_just_after_window_end():
    observation = _obs(
        "fire-1", CUTOFF + timedelta(hours=24, seconds=1)
    )

    records = _labels([observation], CELLS, [CUTOFF])

    assert records[0].target == 0


def test_construct_labels_excludes_low_confidence_observation():
    observation = _obs("fire-1", CUTOFF + timedelta(hours=5), confidence="l")

    records = _labels([observation], CELLS, [CUTOFF])

    assert records[0].target == 0


def test_construct_labels_excludes_observation_outside_the_cell():
    observation = _obs(
        "fire-1", CUTOFF + timedelta(hours=5), latitude=10.0, longitude=10.0
    )

    records = _labels([observation], CELLS, [CUTOFF])

    assert records[0].target == 0


def test_construct_labels_produces_one_record_per_cell_per_cutoff():
    bbox = (-120.0, 37.0, -119.8, 37.2)
    cells = build_california_grid(bbox=bbox, resolution_deg=0.1)
    cutoffs = hourly_cutoffs(CUTOFF, CUTOFF + timedelta(hours=3))

    records = construct_labels([], cells, cutoffs, bbox=bbox)

    assert len(records) == len(cells) * len(cutoffs)

    pairs = {(record.tile_id, record.cutoff) for record in records}
    assert len(pairs) == len(cells) * len(cutoffs)


def test_save_labels_roundtrip(tmp_path):
    records = _labels([], CELLS, [CUTOFF])

    output_path = tmp_path / "labels.csv"
    result = save_labels(records, output_path)

    content = result.read_text(encoding="utf-8")

    assert "tile_id,cutoff,target,qualifying_observation_ids" in content
    assert records[0].tile_id in content
