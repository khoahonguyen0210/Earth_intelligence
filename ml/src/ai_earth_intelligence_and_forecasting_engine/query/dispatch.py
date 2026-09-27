from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests

from ai_earth_intelligence_and_forecasting_engine.data.firms import load_firms_config
from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    build_provenance,
    provenance_to_dict,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.historical_dataset import (
    ERA5History,
)
from ai_earth_intelligence_and_forecasting_engine.planner.validator import (
    Plan,
    PlanStep,
)
from ai_earth_intelligence_and_forecasting_engine.query.forecast_summary import (
    summarize_forecast_result,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import (
    NormalizedRegion,
    normalize_region,
)
from ai_earth_intelligence_and_forecasting_engine.query.run_analysis import (
    load_observations_for,
    run_analysis,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    RegionSpec,
    TimeRangeSpec,
)
from ai_earth_intelligence_and_forecasting_engine.query.statistics import (
    count as count_observations,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)
from ai_earth_intelligence_and_forecasting_engine.rag.embeddings import embed_texts
from ai_earth_intelligence_and_forecasting_engine.rag.index import (
    DEFAULT_INDEX_DIR,
    DocsIndex,
    load_index,
)

if TYPE_CHECKING:
    from google import genai

DEFAULT_FIRMS_HISTORY_DIR = Path("data/raw/firms/history")
DEFAULT_ERA5_HISTORY_DIR = Path("data/raw/era5/history")

_INTENT_FOR_OPERATION = {
    "count": "count",
    "daily_aggregate": "aggregate",
    "weekly_aggregate": "aggregate",
    "map": "map",
}


class StepFailed(Exception):
    """A step could not be executed -- its own error, or a dependency's."""

    def __init__(self, step_id: str, message: str):
        super().__init__(f"step {step_id!r}: {message}")
        self.step_id = step_id


@dataclass(frozen=True)
class Backend:
    """Where run_forecast/get_result_evidence reach the real backend.

    poll_interval_seconds/max_wait_seconds bound how long one
    run_forecast step waits for a terminal status.
    """

    base_url: str
    poll_interval_seconds: float = 1.0
    max_wait_seconds: float = 150.0


def _resolve_region_input(value: dict[str, Any]) -> NormalizedRegion:
    return normalize_region(RegionSpec(kind=value["kind"], value=value["value"]))


def dispatch_resolve_region(step_input: dict[str, Any]) -> dict[str, Any]:
    region = _resolve_region_input(step_input["region"])
    return {
        "bbox": list(region.bbox),
        "geometry": region.geometry,
        "source_kind": region.source_kind,
        "label": region.label,
    }


def dispatch_get_data(step_input: dict[str, Any]) -> dict[str, Any]:
    time_range = normalize_time_range(
        TimeRangeSpec(
            start=step_input["time_range"]["start"], end=step_input["time_range"]["end"]
        )
    )
    dataset = step_input["dataset"]

    if dataset == "firms":
        region = _resolve_region_input(step_input["region"])
        observations = load_observations_for(
            DEFAULT_FIRMS_HISTORY_DIR, time_range.start, time_range.end
        )
        config = load_firms_config()
        provenance = build_provenance(
            source="NASA_FIRMS",
            product=config.product,
            dataset_version="VIIRS_SNPP_SP",
            period_start=time_range.start,
            period_end=time_range.end,
            retrieval_timestamp=datetime.now(timezone.utc),
        )
        return {
            "source": "NASA_FIRMS",
            "product": config.product,
            "record_count": count_observations(observations, region, time_range),
            "provenance": provenance_to_dict(provenance),
        }

    if dataset == "era5_land":
        region = _resolve_region_input(step_input["region"])
        west, south, east, north = region.bbox
        records = [
            record
            for record in ERA5History(DEFAULT_ERA5_HISTORY_DIR).for_cutoff(
                time_range.end
            )
            if west <= record.longitude <= east and south <= record.latitude <= north
        ]
        provenance = build_provenance(
            source="ERA5-Land",
            product="reanalysis-era5-land",
            dataset_version="ERA5-Land",
            period_start=time_range.start,
            period_end=time_range.end,
            retrieval_timestamp=datetime.now(timezone.utc),
        )
        return {
            "source": "ERA5-Land",
            "product": "reanalysis-era5-land",
            "record_count": len(records),
            "provenance": provenance_to_dict(provenance),
        }

    raise ValueError(f"Unsupported dataset: {dataset!r}")


def _run_analysis_step(
    question: str, step_input: dict[str, Any], operation: str
) -> dict[str, Any]:
    payload = {
        "question": question,
        "intent": _INTENT_FOR_OPERATION[operation],
        "region": step_input["region"],
        "time_range": step_input["time_range"],
        "operation": operation,
    }
    return run_analysis(payload, DEFAULT_FIRMS_HISTORY_DIR)


def dispatch_calculate_statistics(
    question: str, step_input: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (result, evidence) separately: result stays exactly the
    shape output_fields promises ({count}/{daily}/{weekly})."""
    payload = _run_analysis_step(question, step_input, step_input["operation"])
    return payload["result"], payload["evidence"]


def dispatch_generate_map(
    question: str, step_input: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _run_analysis_step(question, step_input, "map")
    return payload["result"], payload["evidence"]


def dispatch_run_forecast(
    step_input: dict[str, Any], backend: Backend
) -> dict[str, Any]:
    response = requests.post(
        f"{backend.base_url}/forecasts",
        json={"region": step_input["region"], "cutoff": step_input["cutoff"]},
        timeout=30,
    )
    response.raise_for_status()
    forecast_id = response.json()["forecast_id"]

    deadline = time.monotonic() + backend.max_wait_seconds
    status = "PENDING"
    while time.monotonic() < deadline:
        status_response = requests.get(
            f"{backend.base_url}/forecasts/{forecast_id}", timeout=10
        )
        status_response.raise_for_status()
        status = status_response.json()["status"]
        if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(backend.poll_interval_seconds)
    else:
        raise StepFailed(
            "run_forecast",
            f"forecast {forecast_id} did not finish within {backend.max_wait_seconds}s",
        )

    if status != "SUCCEEDED":
        result_response = requests.get(
            f"{backend.base_url}/forecasts/{forecast_id}/result", timeout=10
        )
        error = (
            result_response.json().get("error", f"forecast ended as {status}")
            if result_response.headers.get("content-type", "").startswith(
                "application/json"
            )
            else status
        )
        raise StepFailed(
            "run_forecast", f"forecast {forecast_id} did not succeed: {error}"
        )

    return {"forecast_id": forecast_id, "status": status}


def _fetch_forecast_result(forecast_id: str, backend: Backend) -> dict[str, Any]:
    """GET /forecasts/{id}/result is 200 only for a SUCCEEDED forecast; a
    409 (not finished yet) or 422 (FAILED) raises via raise_for_status()
    instead. The body is {forecast_id, result}; evidence sits inside
    result."""
    response = requests.get(
        f"{backend.base_url}/forecasts/{forecast_id}/result", timeout=10
    )
    response.raise_for_status()
    return response.json()["result"]


def dispatch_get_result_evidence(
    step_input: dict[str, Any], backend: Backend
) -> dict[str, Any]:
    return _fetch_forecast_result(step_input["result_id"], backend)["evidence"]


def dispatch_get_forecast_result(
    step_input: dict[str, Any], backend: Backend
) -> tuple[dict[str, Any], dict[str, Any]]:
    forecast_id = step_input["result_id"]
    result = _fetch_forecast_result(forecast_id, backend)
    return summarize_forecast_result(forecast_id, result), result["evidence"]


PASSAGE_CHARS = 700
# Dense retrieval measured best on the labelled question set
# (docs/rag.md); without a client it falls back to BM25.
DOCS_SEARCH_MODE = "dense"
_docs_index: DocsIndex | None = None


def _get_docs_index() -> DocsIndex:
    global _docs_index
    if _docs_index is None:
        _docs_index = load_index(DEFAULT_INDEX_DIR)
    return _docs_index


def _no_wait(seconds: float) -> None:
    raise RuntimeError("embedding quota exhausted")


def dispatch_search_docs(
    step_input: dict[str, Any], client: genai.Client | None
) -> dict[str, Any]:
    """Dense search when an embedding is available right now. A request
    is never held waiting on the embedding quota: if the query cannot be
    embedded immediately, it is answered with BM25 and says so."""
    query = step_input["query"]
    index = _get_docs_index()
    retrieval = "lexical"
    query_vector = None
    if client is not None and index.embeddings is not None:
        try:
            query_vector = embed_texts(client, [query], "RETRIEVAL_QUERY", _no_wait)[0]
            retrieval = DOCS_SEARCH_MODE
        except Exception:  # noqa: BLE001 -- any embedding failure falls back to BM25
            retrieval = "lexical (embedding unavailable)"
    passages = index.search(
        query,
        k=5,
        mode=DOCS_SEARCH_MODE if query_vector is not None else "lexical",
        query_vector=query_vector,
    )
    return {
        "query": query,
        "retrieval": retrieval,
        "passages": [
            {
                "source": passage.chunk.source,
                "heading": passage.chunk.heading,
                "text": passage.chunk.text[:PASSAGE_CHARS],
                "score": round(passage.score, 4),
            }
            for passage in passages
        ],
    }


class _ReferencedStepUnavailable(Exception):
    """A "$step_id.field" reference names a step that never produced an
    output -- it failed, or was itself skipped as a dependent of a
    failure. Distinct from StepFailed so execute_plan can tell "this
    step's own logic failed" from "a step it reads from didn't run"."""

    def __init__(self, step_id: str):
        super().__init__(step_id)
        self.step_id = step_id


def _resolve_refs(value: Any, outputs: dict[str, dict[str, Any]]) -> Any:
    """Substitutes every "$step_id.field" string in `value` (recursively,
    through dicts/lists) with that step's real, already-produced output
    value -- the validator already proved every such reference points at
    a real earlier step and a field it really produces (when that step
    ran); this is purely substitution, not a second round of
    validation."""
    if isinstance(value, str) and value.startswith("$"):
        step_id, _, field = value[1:].partition(".")
        if step_id not in outputs:
            raise _ReferencedStepUnavailable(step_id)
        return outputs[step_id][field]
    if isinstance(value, dict):
        return {key: _resolve_refs(nested, outputs) for key, nested in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(nested, outputs) for nested in value]
    return value


def _execute_step(
    step: PlanStep,
    question: str,
    outputs: dict[str, dict[str, Any]],
    backend: Backend,
    client: genai.Client | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Returns (output, evidence). Only calculate_statistics, generate_map
    and get_forecast_result have an evidence record of their own; every
    other tool's evidence is None."""
    try:
        resolved_input = _resolve_refs(step.input, outputs)

        if step.tool == "resolve_region":
            return dispatch_resolve_region(resolved_input), None
        if step.tool == "get_data":
            return dispatch_get_data(resolved_input), None
        if step.tool == "calculate_statistics":
            return dispatch_calculate_statistics(question, resolved_input)
        if step.tool == "generate_map":
            return dispatch_generate_map(question, resolved_input)
        if step.tool == "run_forecast":
            return dispatch_run_forecast(resolved_input, backend), None
        if step.tool == "get_result_evidence":
            return dispatch_get_result_evidence(resolved_input, backend), None
        if step.tool == "get_forecast_result":
            return dispatch_get_forecast_result(resolved_input, backend)
        if step.tool == "search_docs":
            return dispatch_search_docs(resolved_input, client), None
    except _ReferencedStepUnavailable as error:
        raise StepFailed(
            step.step_id, f"dependency {error.step_id!r} did not produce an output"
        ) from error
    except StepFailed:
        raise
    except Exception as error:  # noqa: BLE001 -- surfaced as this step's own failure, not a crash
        raise StepFailed(step.step_id, str(error)) from error

    raise StepFailed(step.step_id, f"unknown tool: {step.tool!r}")


@dataclass(frozen=True)
class PlanExecution:
    """Every step's real output (field-indexable, exactly output_fields'
    shape -- what a later step's "$step.field" reference resolves
    against) and, where a tool has one, its own evidence record."""

    outputs: dict[str, dict[str, Any]]
    evidence: dict[str, dict[str, Any]]


def execute_plan(
    plan: Plan, backend: Backend, client: genai.Client | None = None
) -> PlanExecution:
    """Runs every step of an already-validated Plan (validate_plan_or_raise
    must have passed first) in dependency order. A step whose dependency
    failed is never attempted, and the whole call raises StepFailed
    naming every failure, rather than silently producing a partial
    answer."""
    outputs: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    failed: dict[str, str] = {}

    for step in plan.steps:
        blocked_by = next((dep for dep in step.depends_on if dep in failed), None)
        if blocked_by is not None:
            failed[step.step_id] = f"dependency {blocked_by!r} failed"
            continue

        try:
            output, step_evidence = _execute_step(
                step, plan.question, outputs, backend, client
            )
            outputs[step.step_id] = output
            if step_evidence is not None:
                evidence[step.step_id] = step_evidence
        except StepFailed as error:
            failed[step.step_id] = str(error)

    if failed:
        raise StepFailed(
            next(iter(failed)), "; ".join(f"{k}: {v}" for k, v in failed.items())
        )

    return PlanExecution(outputs=outputs, evidence=evidence)
