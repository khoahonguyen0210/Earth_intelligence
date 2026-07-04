from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

PACKAGE_NAME = "ai-earth-intelligence-and-forecasting-engine"


def get_pipeline_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "unknown"


def compute_file_checksum(path: Path, algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


@dataclass(frozen=True)
class ProvenanceRecord:
    source: str
    product: str
    dataset_version: str
    pipeline_version: str
    retrieval_timestamp: str
    period_start: str | None = None
    period_end: str | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    parameters: dict[str, Any] | None = None


def build_provenance(
    source: str,
    product: str,
    dataset_version: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    retrieval_timestamp: datetime | None = None,
    raw_file_path: Path | None = None,
    checksum_algorithm: str = "sha256",
    parameters: dict[str, Any] | None = None,
) -> ProvenanceRecord:
    checksum = None

    if raw_file_path is not None and raw_file_path.exists():
        checksum = compute_file_checksum(raw_file_path, checksum_algorithm)

    resolved_retrieval_timestamp = retrieval_timestamp or datetime.now(timezone.utc)

    return ProvenanceRecord(
        source=source,
        product=product,
        dataset_version=dataset_version,
        pipeline_version=get_pipeline_version(),
        retrieval_timestamp=resolved_retrieval_timestamp.isoformat(),
        period_start=period_start.isoformat() if period_start else None,
        period_end=period_end.isoformat() if period_end else None,
        checksum=checksum,
        checksum_algorithm=checksum_algorithm if checksum else None,
        parameters=parameters,
    )


def provenance_to_dict(record: ProvenanceRecord) -> dict[str, Any]:
    return {
        "source": record.source,
        "product": record.product,
        "dataset_version": record.dataset_version,
        "pipeline_version": record.pipeline_version,
        "retrieval_timestamp": record.retrieval_timestamp,
        "period_start": record.period_start,
        "period_end": record.period_end,
        "checksum": record.checksum,
        "checksum_algorithm": record.checksum_algorithm,
        "parameters": record.parameters,
    }


def save_provenance(record: ProvenanceRecord, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(provenance_to_dict(record), indent=2),
        encoding="utf-8",
    )

    return output_path
