from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import cdsapi
import xarray as xr
from dotenv import load_dotenv

load_dotenv()

LOCKED_VARIABLES: tuple[str, ...] = (
    "2m_temperature",
    "total_precipitation",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_dewpoint_temperature",
)


@dataclass(frozen=True)
class ERA5Config:
    url: str
    key: str
    dataset: str = "reanalysis-era5-land"
    variables: tuple[str, ...] = LOCKED_VARIABLES


@dataclass(frozen=True)
class ERA5Record:
    latitude: float
    longitude: float
    valid_time: datetime
    temperature_2m: float
    total_precipitation: float
    u_wind_10m: float
    v_wind_10m: float
    dewpoint_2m: float
    source_record: dict[str, str] = field(default_factory=dict)


def load_era5_config() -> ERA5Config:
    url = os.getenv("CDSAPI_URL")
    key = os.getenv("CDSAPI_KEY")

    if not url:
        raise RuntimeError("CDSAPI_URL is not configured")

    if not key:
        raise RuntimeError("CDSAPI_KEY is not configured")

    return ERA5Config(url=url, key=key)


def build_area(bbox: tuple[float, float, float, float]) -> list[float]:
    west, south, east, north = bbox

    return [north, west, south, east]


def fetch_era5_sample(
    config: ERA5Config,
    bbox: tuple[float, float, float, float],
    observed_date: date,
    hour: str,
    output_path: Path,
) -> Path:
    client = cdsapi.Client(url=config.url, key=config.key)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    request = {
        "variable": list(config.variables),
        "year": f"{observed_date.year:04d}",
        "month": f"{observed_date.month:02d}",
        "day": f"{observed_date.day:02d}",
        "time": hour,
        "area": build_area(bbox),
        "data_format": "netcdf",
        "download_format": "unarchived",
    }

    client.retrieve(config.dataset, request, str(output_path))

    return output_path


def parse_era5_records(nc_path: Path) -> list[ERA5Record]:
    dataset = xr.open_dataset(nc_path)

    required_variables = {"t2m", "tp", "u10", "v10", "d2m"}
    missing_variables = required_variables - set(dataset.data_vars)

    if missing_variables:
        raise ValueError(
            f"ERA5-Land NetCDF is missing required variables: "
            f"{sorted(missing_variables)}"
        )

    records: list[ERA5Record] = []

    frame = dataset.to_dataframe().reset_index()

    time_column = "valid_time" if "valid_time" in frame.columns else "time"
    columns = {
        name: frame[name].to_numpy()
        for name in ("latitude", "longitude", "t2m", "tp", "u10", "v10", "d2m")
    }
    valid_times = frame[time_column].dt.to_pydatetime()

    for index in range(len(frame)):
        latitude = float(columns["latitude"][index])
        longitude = float(columns["longitude"][index])

        if not -90 <= latitude <= 90:
            raise ValueError(f"Invalid latitude: {latitude}")

        if not -180 <= longitude <= 180:
            raise ValueError(f"Invalid longitude: {longitude}")

        values = {
            name: float(columns[name][index])
            for name in ("t2m", "tp", "u10", "v10", "d2m")
        }

        records.append(
            ERA5Record(
                latitude=latitude,
                longitude=longitude,
                valid_time=valid_times[index].replace(tzinfo=timezone.utc),
                temperature_2m=values["t2m"],
                total_precipitation=values["tp"],
                u_wind_10m=values["u10"],
                v_wind_10m=values["v10"],
                dewpoint_2m=values["d2m"],
                source_record={name: str(value) for name, value in values.items()},
            )
        )

    dataset.close()

    return records


def relative_humidity_percent(temperature_2m: float, dewpoint_2m: float) -> float:
    t_celsius = temperature_2m - 273.15
    td_celsius = dewpoint_2m - 273.15

    numerator = 17.625 * td_celsius / (243.04 + td_celsius)
    denominator = 17.625 * t_celsius / (243.04 + t_celsius)

    return 100 * math.exp(numerator - denominator)
