from __future__ import annotations

import random
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.drift import (
    PSI_MAJOR,
    SERVING_DRIFT_FEATURES,
    build_reference,
    drift_report,
    load_reference,
    psi,
    save_reference,
)

CUTOFF = datetime(2020, 8, 1, tzinfo=timezone.utc)


def _rows(temperature_shift: float, n: int = 2000, seed: int = 0) -> list[DatasetRow]:
    rng = random.Random(seed)
    return [
        DatasetRow(
            tile_id=f"t{index}",
            cutoff=CUTOFF,
            split="train",
            target=0,
            previous_24h_count=0,
            previous_72h_count=0,
            previous_7d_count=1 if rng.random() < 0.05 else 0,
            previous_30d_count=0,
            neighboring_previous_24h_count=0,
            temperature_2m=290.0 + temperature_shift + rng.gauss(0, 3),
            total_precipitation=rng.random() * 0.002,
            u_wind_10m=rng.gauss(0, 2),
            v_wind_10m=rng.gauss(0, 2),
            relative_humidity=None if index % 50 == 0 else rng.uniform(10, 90),
            elevation_m=rng.uniform(0, 3000),
            slope_deg=rng.uniform(0, 30),
            land_cover_class=rng.choice([10, 30, 60]),
        )
        for index in range(n)
    ]


def test_psi_is_zero_for_identical_distributions_and_grows_with_shift():
    same = psi([0.25, 0.25, 0.5], [0.25, 0.25, 0.5])
    small = psi([0.25, 0.25, 0.5], [0.3, 0.2, 0.5])
    large = psi([0.25, 0.25, 0.5], [0.7, 0.2, 0.1])

    assert same == pytest.approx(0.0)
    assert 0 < small < large


def test_a_fresh_sample_from_the_same_distribution_shows_no_drift():
    reference = build_reference(_rows(0.0, seed=1))

    report = drift_report(reference, _rows(0.0, seed=2))

    assert report["max_psi"] < 0.1
    assert report["major"] == []


def test_a_shifted_temperature_is_flagged_as_major_drift_and_nothing_else():
    reference = build_reference(_rows(0.0, seed=1))

    report = drift_report(reference, _rows(8.0, seed=2))

    assert report["psi"]["temperature_2m"] >= PSI_MAJOR
    assert report["major"] == ["temperature_2m"]


def test_serving_drift_skips_weather_and_still_catches_a_dead_fire_feed():
    reference = build_reference(_rows(0.0, seed=1))
    feed_down = [replace(row, previous_7d_count=0) for row in _rows(8.0, seed=2)]

    report = drift_report(reference, feed_down, SERVING_DRIFT_FEATURES)

    assert "temperature_2m" not in report["psi"]
    assert report["psi"]["previous_7d_count"] > 0
    assert set(report["psi"]) == set(SERVING_DRIFT_FEATURES)


def test_reference_counts_missing_values_in_their_own_bin():
    reference = build_reference(_rows(0.0))

    proportions = reference["features"]["relative_humidity"]["proportions"]
    assert proportions[-1] == pytest.approx(0.02)
    assert sum(proportions) == pytest.approx(1.0)


def test_reference_round_trips_through_the_model_directory(tmp_path):
    reference = build_reference(_rows(0.0))

    assert load_reference(tmp_path) is None
    save_reference(reference, tmp_path)

    assert load_reference(tmp_path) == reference


def test_mostly_zero_count_features_collapse_to_few_edges():
    reference = build_reference(_rows(0.0))

    assert len(reference["features"]["previous_7d_count"]["edges"]) <= 2
    land_cover = reference["features"]["land_cover_class"]["proportions"]
    assert sum(land_cover) == pytest.approx(1.0)
