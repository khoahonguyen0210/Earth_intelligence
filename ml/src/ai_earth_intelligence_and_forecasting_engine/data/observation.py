from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Observation:
    observation_id: str
    source: str
    product: str
    observed_at: datetime
    latitude: float
    longitude: float
    source_record_id: str
    ingested_at: datetime
    quality: float | None = None
    confidence: str | None = None