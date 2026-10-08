from __future__ import annotations

from datetime import date

import pytest

from ai_earth_intelligence_and_forecasting_engine.models.auto_retrain import (
    Steps,
    latest_complete_season,
    pending_seasons,
    run_pending,
)
from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    ModelRegistry,
)


def _registry(tmp_path, gates=()):
    registry = ModelRegistry(tmp_path / "registry")
    for gate in gates:
        registry.record_run({"seasons": {"gate": gate}, "candidate": f"s{gate}"})
    return registry


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 5), 2025),
        (date(2026, 2, 1), 2025),
        (date(2026, 1, 31), 2024),
        (date(2027, 3, 1), 2026),
        (date(2025, 6, 1), 2024),
    ],
)
def test_a_season_counts_as_complete_only_after_the_data_lag(today, expected):
    assert latest_complete_season(today) == expected


def test_nothing_is_pending_until_a_season_after_the_locked_one_is_complete(
    tmp_path,
):
    assert pending_seasons(_registry(tmp_path), date(2025, 12, 31)) == []


def test_every_unprocessed_complete_season_is_pending_in_order(tmp_path):
    registry = _registry(tmp_path, gates=[2025])

    assert pending_seasons(registry, date(2028, 3, 1)) == [2026, 2027]


def test_a_processed_season_is_never_pending_again(tmp_path):
    registry = _registry(tmp_path, gates=[2025])

    assert pending_seasons(registry, date(2026, 10, 5)) == []


def test_run_pending_does_each_step_per_season_in_order(tmp_path):
    registry = _registry(tmp_path)
    calls: list[tuple[str, int]] = []

    def record(name):
        def step(season):
            calls.append((name, season))
            return {"candidate": f"s{season}"}

        return step

    steps = Steps(
        download=record("download"), build=record("build"), retrain=record("retrain")
    )

    results = run_pending(registry, date(2027, 3, 1), steps)

    assert calls == [
        ("download", 2025),
        ("build", 2025),
        ("retrain", 2025),
        ("download", 2026),
        ("build", 2026),
        ("retrain", 2026),
    ]
    assert [result["candidate"] for result in results] == ["s2025", "s2026"]


def test_run_pending_with_nothing_to_do_calls_no_step(tmp_path):
    registry = _registry(tmp_path, gates=[2025])

    def boom(season):
        raise AssertionError("no step should run")

    results = run_pending(
        registry, date(2026, 10, 5), Steps(download=boom, build=boom, retrain=boom)
    )

    assert results == []


def test_a_failing_download_stops_before_any_training(tmp_path):
    registry = _registry(tmp_path)
    trained: list[int] = []

    def failing(season):
        raise RuntimeError("download failed")

    steps = Steps(
        download=failing,
        build=lambda season: None,
        retrain=lambda season: trained.append(season) or {},
    )

    with pytest.raises(RuntimeError, match="download failed"):
        run_pending(registry, date(2026, 10, 5), steps)

    assert trained == []
