from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    get_pipeline_version,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import NormalizedRegion
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    StructuredEarthQuery,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    NormalizedTimeRange,
)


@dataclass(frozen=True)
class Evidence:
    dataset: str
    period_start: str
    period_end: str
    region_kind: str
    region_label: str | None
    region_bbox: tuple[float, float, float, float]
    query_parameters: dict[str, Any]
    processing_version: str


def build_evidence(
    dataset: str,
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
    query_parameters: dict[str, Any],
) -> Evidence:
    return Evidence(
        dataset=dataset,
        period_start=time_range.start.isoformat(),
        period_end=time_range.end.isoformat(),
        region_kind=region.source_kind,
        region_label=region.label,
        region_bbox=region.bbox,
        query_parameters=query_parameters,
        processing_version=get_pipeline_version(),
    )


def build_evidence_from_query(
    query: StructuredEarthQuery,
    dataset: str,
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
) -> Evidence:
    return build_evidence(
        dataset=dataset,
        region=region,
        time_range=time_range,
        query_parameters={
            "question": query.question,
            "intent": query.intent.value,
            "operation": query.operation,
        },
    )


def evidence_to_dict(evidence: Evidence) -> dict[str, Any]:
    return {
        "dataset": evidence.dataset,
        "period_start": evidence.period_start,
        "period_end": evidence.period_end,
        "region_kind": evidence.region_kind,
        "region_label": evidence.region_label,
        "region_bbox": list(evidence.region_bbox),
        "query_parameters": evidence.query_parameters,
        "processing_version": evidence.processing_version,
    }


def attach_evidence(result: Any, evidence: Evidence) -> dict[str, Any]:
    return {
        "result": result,
        "evidence": evidence_to_dict(evidence),
    }
