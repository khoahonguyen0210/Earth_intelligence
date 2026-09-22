from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    ERA5Config,
    ERA5Record,
    fetch_era5_sample,
    load_era5_config,
    parse_era5_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    FIRMSConfig,
    load_firms_config,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import CALIFORNIA_BBOX
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    LOOKBACK_HOURS,
    fetch_firms_span,
    firms_spans,
)

LIVE_FIRMS_PRODUCT = "VIIRS_SNPP_NRT"
LIVE_MAX_CUTOFF_AGE = timedelta(days=60)
ERA5_LAG_DAYS = (5, 6, 7)


def check_live_cutoff(cutoff: datetime, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if now - cutoff > LIVE_MAX_CUTOFF_AGE:
        raise ValueError(
            f"cutoff {cutoff.isoformat()} is older than the live data window "
            f"({LIVE_MAX_CUTOFF_AGE.days} days) and outside the saved history "
            f"(May 2 - October 27 of 2019-2024)"
        )


def ensure_live_firms(
    live_dir: Path,
    cutoff: datetime,
    config: FIRMSConfig | None = None,
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
    today: date | None = None,
) -> None:
    """Downloads the near-real-time FIRMS spans covering the cutoff's
    lookback into `live_dir`. A span ending before today is final and is
    reused; one reaching today is fetched again."""
    config = config or load_firms_config()
    config = FIRMSConfig(map_key=config.map_key, product=LIVE_FIRMS_PRODUCT)
    today = today or datetime.now(timezone.utc).date()

    day = (cutoff - timedelta(hours=LOOKBACK_HOURS)).date()
    days = []
    while day <= cutoff.date():
        days.append(day)
        day += timedelta(days=1)

    for span in firms_spans(days):
        path = live_dir / span.file_name
        if path.exists() and span.end < today:
            continue
        fetch_firms_span(config, bbox, span, path)


def live_era5_file_name(day: date, hour: int) -> str:
    return f"era5_land_live_{day.isoformat()}_{hour:02d}.nc"


def ensure_live_era5(
    live_dir: Path,
    cutoff: datetime,
    config: ERA5Config | None = None,
    bbox: tuple[float, float, float, float] = CALIFORNIA_BBOX,
) -> list[ERA5Record]:
    """The newest ERA5-Land hour available for the cutoff. ERA5-Land
    publishes a few days late, so the most recent days are tried first."""
    last_error: Exception | None = None

    for lag in ERA5_LAG_DAYS:
        day = (cutoff - timedelta(days=lag)).date()
        path = live_dir / live_era5_file_name(day, cutoff.hour)
        try:
            if not path.exists():
                config = config or load_era5_config()
                fetch_era5_sample(config, bbox, day, f"{cutoff.hour:02d}:00", path)
            return parse_era5_records(path)
        except Exception as error:
            last_error = error
            path.unlink(missing_ok=True)

    raise RuntimeError(
        f"no ERA5-Land weather available for the {ERA5_LAG_DAYS[0]}-"
        f"{ERA5_LAG_DAYS[-1]} days before {cutoff.isoformat()}: {last_error}"
    ) from last_error
