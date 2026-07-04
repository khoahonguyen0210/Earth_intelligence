from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from ai_earth_intelligence_and_forecasting_engine.data.observation import (
    Observation,
)

load_dotenv()

@dataclass(frozen=True)
class FIRMSConfig:
    map_key: str
    product: str = "VIIRS_SNPP_SP"
    base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area"

@dataclass(frozen=True)
class FIRMSRecord:
    latitude: float
    longitude: float
    observed_at: datetime
    source_record: dict[str, str]

def normalize_firms_record(
    record: FIRMSRecord,
    product: str,
    source_record_id: str,
    ingested_at: datetime,
) -> Observation:
    return Observation(
        observation_id=f"firms:{source_record_id}",
        source="NASA_FIRMS",
        product=product,
        observed_at=record.observed_at,
        latitude=record.latitude,
        longitude=record.longitude,
        source_record_id=source_record_id,
        ingested_at=ingested_at,
        confidence=record.source_record.get("confidence"),
    )

def load_firms_config() -> FIRMSConfig:
    map_key = os.getenv("FIRMS_MAP_KEY")

    if not map_key:
        raise RuntimeError("FIRMS_MAP_KEY is not configured")

    return FIRMSConfig(map_key=map_key)


def build_area_url(
    config: FIRMSConfig,
    bbox: tuple[float, float, float, float],
    observed_date: date,
) -> str:
    west, south, east, north = bbox
    area = f"{west},{south},{east},{north}"

    return (
        f"{config.base_url}/csv/"
        f"{config.map_key}/"
        f"{config.product}/"
        f"{area}/"
        f"1/"
        f"{observed_date.isoformat()}"
    )


def fetch_firms_sample(
    config: FIRMSConfig,
    bbox: tuple[float, float, float, float],
    observed_date: date,
    output_path: Path,
) -> Path:
    url = build_area_url(config, bbox, observed_date)

    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == max_retries - 1:
                    response.raise_for_status()

                time.sleep(2**attempt)
                continue

            response.raise_for_status()
            break

        except (requests.ConnectionError, requests.Timeout):
            if attempt == max_retries - 1:
                raise

            time.sleep(2**attempt)

    records = parse_firms_records(response.text)
    print("Parsed records:", len(records))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.text, encoding="utf-8")
    
    return output_path

def parse_firms_records(csv_text: str) -> list[FIRMSRecord]:
    reader = csv.DictReader(csv_text.splitlines())

    if reader.fieldnames is None:
        raise ValueError("FIRMS CSV has no header")

    required_fields = {
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
    }

    missing_fields = required_fields - set(reader.fieldnames)

    if missing_fields:
        raise ValueError(
            f"FIRMS CSV is missing required fields: {sorted(missing_fields)}"
        )

    records: list[FIRMSRecord] = []

    for row in reader:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])

        if not -90 <= latitude <= 90:
            raise ValueError(f"Invalid latitude: {latitude}")

        if not -180 <= longitude <= 180:
            raise ValueError(f"Invalid longitude: {longitude}")

        observed_at = datetime.strptime(
            f"{row['acq_date']} {row['acq_time'].zfill(4)}",
            "%Y-%m-%d %H%M",
        ).replace(tzinfo=timezone.utc)

        records.append(
            FIRMSRecord(
                latitude=latitude,
                longitude=longitude,
                observed_at=observed_at,
                source_record=dict(row),
            )
        )

    return records
