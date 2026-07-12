from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Locked per docs/forecasting-specification.md and
# project-context/PROJECT_BIBLE.md section 3. Do not alter for the main
# benchmark.

FORECAST_WINDOW_HOURS = 24


@dataclass(frozen=True)
class SplitRange:
    start: date
    end: date  # inclusive


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
