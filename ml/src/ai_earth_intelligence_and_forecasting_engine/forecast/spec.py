from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FORECAST_WINDOW_HOURS = 24


@dataclass(frozen=True)
class SplitRange:
    start: date
    end: date


TRAIN_SPLIT = SplitRange(date(2019, 1, 1), date(2022, 12, 31))
VALIDATION_SPLIT = SplitRange(date(2023, 1, 1), date(2023, 12, 31))
TEST_SPLIT = SplitRange(date(2024, 1, 1), date(2024, 12, 31))


def split_for_date(target_date: date) -> str | None:
    if TRAIN_SPLIT.start <= target_date <= TRAIN_SPLIT.end:
        return "train"

    if VALIDATION_SPLIT.start <= target_date <= VALIDATION_SPLIT.end:
        return "validation"

    if TEST_SPLIT.start <= target_date <= TEST_SPLIT.end:
        return "test"

    return None
