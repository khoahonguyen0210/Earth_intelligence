"""Real historical Earth data for the locked 2019-2024 split.

Before this module the project had ingested exactly one real day of FIRMS
detections (2024-08-15) and one real ERA5-Land hour, so the train and
validation splits contained no real positive examples and every model in
the ladder was untrainable on real data (docs/feature-set-freeze.md).
This module defines, *before* any model is trained on the result, which
historical cutoffs the benchmark dataset samples and exactly which raw
FIRMS days and ERA5-Land hours those cutoffs need -- see
docs/historical-dataset.md for the reasoning.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    FIRMSConfig,
    normalize_firms_record,
    parse_firms_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast.fire_history_features import (
    FIRE_HISTORY_WINDOWS_HOURS,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    FORECAST_WINDOW_HOURS,
)

# --- The pre-registered cutoff sample --------------------------------------
#
# The spec allows a forecast at every hourly cutoff, but a dataset of every
# hour x 9,975 cells x 6 years (~524M rows) is not buildable here. The
# benchmark therefore samples cutoffs with one fixed rule, identical for
# every year and chosen before any model result exists:
#
#   10:00 UTC, every 7 days from June 1, while still in October.
#
# Fire season (June-October) is where California's fire occurrence is;
# a year-round sample would be dominated by near-certain negatives. 10:00
# UTC matches every earlier real sample and demo cutoff in this project.
FIRE_SEASON_START_MONTH = 6
FIRE_SEASON_END_MONTH = 10
CUTOFF_HOUR_UTC = 10
CUTOFF_STRIDE_DAYS = 7
HISTORY_START_YEAR = 2019
HISTORY_END_YEAR = 2024

# FIRMS' area API rejects day_range outside 1..5 (observed directly:
# "Invalid day range. Expects [1..5].").
FIRMS_MAX_DAY_RANGE = 5

LOOKBACK_HOURS = max(FIRE_HISTORY_WINDOWS_HOURS.values())


def historical_cutoffs(
    start_year: int = HISTORY_START_YEAR, end_year: int = HISTORY_END_YEAR
) -> list[datetime]:
    cutoffs: list[datetime] = []
    for year in range(start_year, end_year + 1):
        cutoff = datetime(
            year, FIRE_SEASON_START_MONTH, 1, CUTOFF_HOUR_UTC, tzinfo=timezone.utc
        )
        while cutoff.month <= FIRE_SEASON_END_MONTH:
            cutoffs.append(cutoff)
            cutoff += timedelta(days=CUTOFF_STRIDE_DAYS)
    return cutoffs


def observation_window(cutoff: datetime) -> tuple[datetime, datetime]:
    """The only observation times that can affect `cutoff`'s row: the
    longest fire-history lookback (cutoff - 30d, cutoff] plus the label
    window (cutoff, cutoff + 24h]. Returned half-open as (start, end]."""
    return (
        cutoff - timedelta(hours=LOOKBACK_HOURS),
        cutoff + timedelta(hours=FORECAST_WINDOW_HOURS),
    )


def required_firms_days(cutoffs: Iterable[datetime]) -> list[date]:
    days: set[date] = set()
    for cutoff in cutoffs:
        start, end = observation_window(cutoff)
        day = start.date()
        while day <= end.date():
            days.add(day)
            day += timedelta(days=1)
    return sorted(days)


@dataclass(frozen=True)
class FIRMSSpan:
    start: date
    day_range: int

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.day_range - 1)

    @property
    def file_name(self) -> str:
        return f"VIIRS_SNPP_SP_{self.start.isoformat()}_{self.day_range}d.csv"


def firms_spans(days: Iterable[date]) -> list[FIRMSSpan]:
    """Consecutive days grouped into requests of at most FIRMS_MAX_DAY_RANGE."""
    spans: list[FIRMSSpan] = []
    run: list[date] = []

    def flush() -> None:
        for index in range(0, len(run), FIRMS_MAX_DAY_RANGE):
            chunk = run[index : index + FIRMS_MAX_DAY_RANGE]
            spans.append(FIRMSSpan(start=chunk[0], day_range=len(chunk)))

    for day in sorted(set(days)):
        if run and day != run[-1] + timedelta(days=1):
            flush()
            run = []
        run.append(day)
    if run:
        flush()
    return spans


def build_span_url(
    config: FIRMSConfig, bbox: tuple[float, float, float, float], span: FIRMSSpan
) -> str:
    west, south, east, north = bbox
    return (
        f"{config.base_url}/csv/{config.map_key}/{config.product}/"
        f"{west},{south},{east},{north}/{span.day_range}/{span.start.isoformat()}"
    )


def fetch_firms_span(
    config: FIRMSConfig,
    bbox: tuple[float, float, float, float],
    span: FIRMSSpan,
    output_path: Path,
    max_retries: int = 4,
) -> Path:
    """One FIRMS area request for `span`, written verbatim to `output_path`.

    Validated before writing: the response must parse as FIRMS CSV and
    every row's acq_date must fall inside the span, so a truncated or
    wrong-window response is never saved as if it were real data."""
    url = build_span_url(config, bbox, span)
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=120)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"FIRMS returned {response.status_code}")
            response.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as error:
            # The map key is part of the URL; never let it reach an error
            # message (docs/structured-logging.md, "Never log secrets").
            last_error = RuntimeError(str(error).replace(config.map_key, "***"))
            time.sleep(2**attempt)
    else:
        raise RuntimeError(f"FIRMS span {span.file_name} failed") from last_error

    records = parse_firms_records(response.text)
    for record in records:
        if not span.start <= record.observed_at.date() <= span.end:
            raise ValueError(
                f"FIRMS returned {record.observed_at.date()} outside {span.file_name}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.text, encoding="utf-8")
    return output_path


def load_firms_history(
    history_dir: Path,
    start: datetime,
    end: datetime,
    product: str = "VIIRS_SNPP_SP",
) -> list[Observation]:
    """Every observation with start < observed_at <= end, from the span
    files under `history_dir` that overlap that window.

    Observation ids embed the span file name, so ids stay unique across
    files (the single-file loader's per-file row index would collide)."""
    ingested_at = datetime.now(timezone.utc)
    observations: list[Observation] = []

    for path in sorted(history_dir.glob("VIIRS_SNPP_SP_*_*d.csv")):
        span = parse_span_file_name(path.name)
        if span.end < start.date() or span.start > end.date():
            continue

        for index, record in enumerate(parse_firms_records(path.read_text("utf-8"))):
            if start < record.observed_at <= end:
                observations.append(
                    normalize_firms_record(
                        record=record,
                        product=product,
                        source_record_id=f"{path.stem}:{index}",
                        ingested_at=ingested_at,
                    )
                )

    return observations


def parse_span_file_name(name: str) -> FIRMSSpan:
    stem = name.removesuffix(".csv")
    _, _, _, start, days = stem.split("_")
    return FIRMSSpan(start=date.fromisoformat(start), day_range=int(days.removesuffix("d")))


def firms_covered_days(history_dir: Path) -> set[date]:
    """Every UTC day some downloaded span file covers."""
    days: set[date] = set()
    for path in history_dir.glob("VIIRS_SNPP_SP_*_*d.csv"):
        span = parse_span_file_name(path.name)
        days.update(span.start + timedelta(days=i) for i in range(span.day_range))
    return days


def require_firms_coverage(
    history_dir: Path, start: datetime, end: datetime, purpose: str
) -> None:
    """Raise unless real FIRMS history covers every UTC day in [start, end].

    The history holds fire seasons only (May 2 - Oct 27, 2019-2024). A day
    outside it has no data, which is not the same as no fires -- counting
    it as zero would fabricate an observation, so callers refuse instead
    (PROJECT_BIBLE.md: never silently fill missing data)."""
    covered = firms_covered_days(history_dir)
    if not covered:
        raise ValueError(f"no FIRMS history found in {history_dir}")
    span_days = (end.date() - start.date()).days + 1
    needed = {start.date() + timedelta(days=i) for i in range(span_days)}
    missing = sorted(needed - covered)
    if missing:
        years = sorted({day.year for day in covered})
        raise ValueError(
            f"no real FIRMS fire history for {purpose} (first uncovered day "
            f"{missing[0].isoformat()}); history covers May 2 - October 27 of "
            f"{years[0]}-{years[-1]}"
        )


# --- ERA5-Land ---------------------------------------------------------------


def required_era5_requests(
    cutoffs: Iterable[datetime],
) -> list[tuple[int, int, list[int], str]]:
    """One CDS request per (year, month): the cutoff days in that month at
    the cutoff hour. Each cutoff's environmental features use the latest
    ERA5-Land record with valid_time <= cutoff (environmental_features.py),
    so the record at exactly the cutoff hour is the one that matters."""
    by_month: dict[tuple[int, int], set[int]] = {}
    hours: set[int] = set()
    for cutoff in cutoffs:
        by_month.setdefault((cutoff.year, cutoff.month), set()).add(cutoff.day)
        hours.add(cutoff.hour)
    if len(hours) != 1:
        raise ValueError(f"expected one cutoff hour, got {sorted(hours)}")
    hour = f"{hours.pop():02d}:00"
    return [
        (year, month, sorted(days), hour)
        for (year, month), days in sorted(by_month.items())
    ]


def era5_file_name(year: int, month: int) -> str:
    return f"era5_land_{year:04d}_{month:02d}.nc"
