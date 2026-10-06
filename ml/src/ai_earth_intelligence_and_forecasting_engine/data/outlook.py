from __future__ import annotations

import math
import time
from datetime import datetime, timedelta

import requests

from ai_earth_intelligence_and_forecasting_engine.data.era5 import ERA5Record
from ai_earth_intelligence_and_forecasting_engine.data.grid import GridCell

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OUTLOOK_MAX_DAYS = 7
SAMPLE_STEP_DEG = 0.5
BATCH_SIZE = 100
HOURLY_VARIABLES = (
    "temperature_2m,dew_point_2m,precipitation,wind_speed_10m,wind_direction_10m"
)


def _snap(value: float) -> float:
    return round(round(value / SAMPLE_STEP_DEG) * SAMPLE_STEP_DEG, 6)


def sample_points(cells: list[GridCell]) -> list[tuple[float, float]]:
    return sorted({(_snap(c.centroid_lat), _snap(c.centroid_lon)) for c in cells})


def wind_components(speed_ms: float, direction_deg: float) -> tuple[float, float]:
    radians = math.radians(direction_deg)
    return -speed_ms * math.sin(radians), -speed_ms * math.cos(radians)


def record_from_hourly(
    hourly: dict, hour: int, latitude: float, longitude: float, valid_time: datetime
) -> ERA5Record:
    speed = hourly["wind_speed_10m"][hour]
    direction = hourly["wind_direction_10m"][hour]
    u_wind, v_wind = wind_components(speed, direction)
    precipitation_mm = sum(
        value or 0.0 for value in hourly["precipitation"][: hour + 1]
    )

    return ERA5Record(
        latitude=latitude,
        longitude=longitude,
        valid_time=valid_time,
        temperature_2m=hourly["temperature_2m"][hour] + 273.15,
        total_precipitation=precipitation_mm / 1000,
        u_wind_10m=u_wind,
        v_wind_10m=v_wind,
        dewpoint_2m=hourly["dew_point_2m"][hour] + 273.15,
    )


def _fetch_batch(
    points: list[tuple[float, float]], day: str, max_retries: int = 4
) -> list[dict]:
    params = {
        "latitude": ",".join(str(lat) for lat, _ in points),
        "longitude": ",".join(str(lon) for _, lon in points),
        "hourly": HOURLY_VARIABLES,
        "wind_speed_unit": "ms",
        "timezone": "GMT",
        "start_date": day,
        "end_date": day,
    }
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = requests.get(OPEN_METEO_URL, params=params, timeout=60)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"Open-Meteo returned {response.status_code}")
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else [payload]
        except (
            requests.ConnectionError,
            requests.Timeout,
            requests.HTTPError,
        ) as error:
            last_error = error
            time.sleep(2**attempt)

    raise RuntimeError("Open-Meteo weather forecast request failed") from last_error


def fetch_weather_outlook(
    cells: list[GridCell], cutoff: datetime, valid_time: datetime
) -> list[ERA5Record]:
    points = sample_points(cells)
    day = cutoff.date().isoformat()
    by_point: dict[tuple[float, float], dict] = {}

    for index in range(0, len(points), BATCH_SIZE):
        batch = points[index : index + BATCH_SIZE]
        for point, location in zip(batch, _fetch_batch(batch, day), strict=True):
            by_point[point] = location["hourly"]

    records = []
    for cell in cells:
        hourly = by_point[(_snap(cell.centroid_lat), _snap(cell.centroid_lon))]
        if hourly["temperature_2m"][cutoff.hour] is None:
            continue
        records.append(
            record_from_hourly(
                hourly, cutoff.hour, cell.centroid_lat, cell.centroid_lon, valid_time
            )
        )

    if not records:
        raise ValueError(f"no weather forecast available for {cutoff.isoformat()}")

    return records


def check_outlook_cutoff(cutoff: datetime, now: datetime) -> None:
    if cutoff - now > timedelta(days=OUTLOOK_MAX_DAYS):
        raise ValueError(
            f"cutoff {cutoff.isoformat()} is more than {OUTLOOK_MAX_DAYS} days "
            f"ahead of now ({now.isoformat()}); forecasts reach at most "
            f"{OUTLOOK_MAX_DAYS} days out"
        )
