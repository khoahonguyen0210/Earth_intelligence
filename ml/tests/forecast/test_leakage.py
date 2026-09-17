"""Consolidated leakage-safety tests.

Checklist of properties and where each is verified:

[x] future timestamps excluded
    -- test_fire_history_features_never_uses_future_timestamps
    -- test_environmental_features_never_uses_future_timestamps
[x] future target excluded
    -- test_label_target_never_uses_observations_at_or_before_cutoff
[x] train/validation/test do not overlap
    -- test_train_validation_test_splits_partition_every_day_exactly_once
[x] feature windows stop at cutoff
    -- test_fire_history_windows_never_extend_past_cutoff
    -- test_environmental_feature_never_uses_record_after_cutoff
[x] learned preprocessing uses training data only
    -- ml/tests/models/test_preprocessing.py::
    test_transform_uses_train_statistics_not_the_input_rows_own_distribution.
"""

import random
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from ai_earth_intelligence_and_forecasting_engine.data.era5 import ERA5Record
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    environmental_features as ef,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    fire_history_features as fhf,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import labels as lb
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    TEST_SPLIT,
    TRAIN_SPLIT,
    VALIDATION_SPLIT,
    split_for_date,
)

RNG_SEED = 20240815
CUTOFF = datetime(2024, 8, 15, 12, 0, tzinfo=timezone.utc)
TEST_BBOX = (-120.0, 37.0, -119.9, 37.1)  # single cell
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)
TILE = CELLS[0].tile_id


def _random_observation(rng: random.Random, index: int) -> Observation:
    offset_hours = rng.uniform(-24 * 40, 24 * 40)  # +/- 40 days around CUTOFF
    return Observation(
        observation_id=f"obs-{index}",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=CUTOFF + timedelta(hours=offset_hours),
        latitude=37.05,
        longitude=-119.95,
        source_record_id=f"obs-{index}",
        ingested_at=CUTOFF,
        confidence="n",
    )


def _random_era5_record(rng: random.Random, index: int) -> ERA5Record:
    offset_hours = rng.uniform(-24 * 10, 24 * 10)
    return ERA5Record(
        latitude=37.05,
        longitude=-119.95,
        valid_time=CUTOFF + timedelta(hours=offset_hours),
        temperature_2m=280.0 + index,
        total_precipitation=0.0,
        u_wind_10m=1.0,
        v_wind_10m=1.0,
        dewpoint_2m=270.0,
    )


def test_fire_history_features_never_uses_future_timestamps():
    rng = random.Random(RNG_SEED)
    observations = [_random_observation(rng, i) for i in range(200)]

    windows_only_up_to_cutoff = [
        obs for obs in observations if obs.observed_at <= CUTOFF
    ]
    future_leaking_in = [
        obs for obs in observations if obs.observed_at > CUTOFF
    ]
    assert future_leaking_in, "test setup must include future observations"

    features_with_all = fhf.compute_fire_history_features(
        observations, CELLS, [CUTOFF], bbox=TEST_BBOX
    )
    features_without_future = fhf.compute_fire_history_features(
        windows_only_up_to_cutoff, CELLS, [CUTOFF], bbox=TEST_BBOX
    )

    assert features_with_all == features_without_future


def test_environmental_features_never_uses_future_timestamps():
    rng = random.Random(RNG_SEED + 1)
    records = [_random_era5_record(rng, i) for i in range(50)]

    past_only = [r for r in records if r.valid_time <= CUTOFF]
    future_records = [r for r in records if r.valid_time > CUTOFF]
    assert future_records, "test setup must include future records"

    with_all = ef.compute_environmental_features(
        records, CELLS, [CUTOFF], bbox=TEST_BBOX
    )
    without_future = ef.compute_environmental_features(
        past_only, CELLS, [CUTOFF], bbox=TEST_BBOX
    )

    assert with_all == without_future


def test_fire_history_windows_never_extend_past_cutoff():
    """For every window length, manually recompute the count using only
    observations strictly inside (cutoff - window, cutoff] and check it
    matches the library's output -- proving the implementation's window
    boundary is exactly what it claims, not off-by-some-amount."""
    rng = random.Random(RNG_SEED + 2)
    observations = [_random_observation(rng, i) for i in range(300)]

    records = fhf.compute_fire_history_features(
        observations, CELLS, [CUTOFF], bbox=TEST_BBOX
    )
    record = next(r for r in records if r.tile_id == TILE)

    for feature_name, window_hours in fhf.FIRE_HISTORY_WINDOWS_HOURS.items():
        window_start = CUTOFF - timedelta(hours=window_hours)
        expected = sum(
            1
            for obs in observations
            if window_start < obs.observed_at <= CUTOFF
        )
        assert getattr(record, feature_name) == expected, feature_name


def test_environmental_feature_never_uses_record_after_cutoff():
    rng = random.Random(RNG_SEED + 3)
    records = [_random_era5_record(rng, i) for i in range(50)]

    eligible = [r for r in records if r.valid_time <= CUTOFF]
    expected_latest = max(eligible, key=lambda r: r.valid_time, default=None)

    result = ef.compute_environmental_features(
        records, CELLS, [CUTOFF], bbox=TEST_BBOX
    )[0]

    if expected_latest is None:
        assert result.temperature_2m is None
    else:
        assert result.temperature_2m == expected_latest.temperature_2m
        assert result.era5_valid_time == expected_latest.valid_time.isoformat()


def test_label_target_never_uses_observations_at_or_before_cutoff():
    """The forward label window is (cutoff, cutoff+24h] -- an observation
    dated at or before the cutoff must never contribute to the target,
    no matter how many of them exist."""
    rng = random.Random(RNG_SEED + 4)
    only_past_or_present = [
        replace(
            _random_observation(rng, i),
            observed_at=CUTOFF - timedelta(hours=rng.uniform(0, 24 * 60)),
        )
        for i in range(100)
    ]

    records = lb.construct_labels(
        only_past_or_present, CELLS, [CUTOFF], bbox=TEST_BBOX
    )

    assert all(record.target == 0 for record in records)
    assert all(record.qualifying_observation_ids == () for record in records)


def test_label_target_only_reflects_the_forward_window():
    rng = random.Random(RNG_SEED + 5)
    observations = [_random_observation(rng, i) for i in range(300)]

    window_end = CUTOFF + timedelta(hours=24)
    expected_qualifying = {
        obs.observation_id
        for obs in observations
        if CUTOFF < obs.observed_at <= window_end
        and lb.is_qualifying_observation(obs)
    }

    records = lb.construct_labels(observations, CELLS, [CUTOFF], bbox=TEST_BBOX)
    record = next(r for r in records if r.tile_id == TILE)

    assert set(record.qualifying_observation_ids) == expected_qualifying
    assert record.target == (1 if expected_qualifying else 0)


def test_train_validation_test_splits_partition_every_day_exactly_once():
    start = TRAIN_SPLIT.start
    end = TEST_SPLIT.end
    total_days = (end - start).days + 1

    assignments: dict[date, str] = {}
    current = start

    while current <= end:
        split = split_for_date(current)
        assert split is not None, f"{current} was not assigned to any split"
        assignments[current] = split
        current += timedelta(days=1)

    assert len(assignments) == total_days  # every day assigned, none skipped

    train_days = sum(1 for s in assignments.values() if s == "train")
    validation_days = sum(1 for s in assignments.values() if s == "validation")
    test_days = sum(1 for s in assignments.values() if s == "test")

    assert train_days == (TRAIN_SPLIT.end - TRAIN_SPLIT.start).days + 1
    assert validation_days == (VALIDATION_SPLIT.end - VALIDATION_SPLIT.start).days + 1
    assert test_days == (TEST_SPLIT.end - TEST_SPLIT.start).days + 1
    assert train_days + validation_days + test_days == total_days


def test_dates_outside_the_locked_range_belong_to_no_split():
    assert split_for_date(TRAIN_SPLIT.start - timedelta(days=1)) is None
    assert split_for_date(TEST_SPLIT.end + timedelta(days=1)) is None


def test_no_single_date_matches_more_than_one_split_boundary_directly():
    """Directly re-check the three transition dates without relying on
    split_for_date, as a second independent confirmation."""
    assert TRAIN_SPLIT.end != VALIDATION_SPLIT.start
    assert VALIDATION_SPLIT.end != TEST_SPLIT.start
    assert TRAIN_SPLIT.end < VALIDATION_SPLIT.start
    assert VALIDATION_SPLIT.end < TEST_SPLIT.start
