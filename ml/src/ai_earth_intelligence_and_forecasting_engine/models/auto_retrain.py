from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    LOCKED_TEST_SEASON,
    ModelRegistry,
)

SEASON_READY_MONTH = 2
SEASON_READY_DAY = 1


def latest_complete_season(today: date) -> int:
    ready_this_year = date(today.year, SEASON_READY_MONTH, SEASON_READY_DAY)
    return today.year - 1 if today >= ready_this_year else today.year - 2


def processed_seasons(registry: ModelRegistry) -> set[int]:
    return {int(run["seasons"]["gate"]) for run in registry.state["runs"]}


def pending_seasons(registry: ModelRegistry, today: date) -> list[int]:
    latest = latest_complete_season(today)
    done = processed_seasons(registry)
    return [
        season
        for season in range(LOCKED_TEST_SEASON + 1, latest + 1)
        if season not in done
    ]


@dataclass(frozen=True)
class Steps:
    download: Callable[[int], None]
    build: Callable[[int], None]
    retrain: Callable[[int], dict[str, Any]]


def run_pending(
    registry: ModelRegistry, today: date, steps: Steps
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for season in pending_seasons(registry, today):
        steps.download(season)
        steps.build(season)
        results.append(steps.retrain(season))
    return results
