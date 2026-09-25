from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    GridCell,
    cell_to_feature,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import (
    FORECAST_WINDOW_HOURS,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    CALIBRATION_METHOD,
    MODEL_VERSION,
    CalibrationBin,
)
from ai_earth_intelligence_and_forecasting_engine.models.explain import (
    FeatureContribution,
)
from ai_earth_intelligence_and_forecasting_engine.query.evidence import (
    Evidence,
    build_evidence,
    evidence_to_dict,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import NormalizedRegion
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    VALID_REGION_KINDS,
    RegionSpec,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    NormalizedTimeRange,
)

FORECAST_STATUS_VALUES: tuple[str, ...] = (
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "RETRYING",
    "CANCELLED",
)

SYNCHRONOUS_STATUS_VALUES: tuple[str, ...] = ("SUCCEEDED", "FAILED")


@dataclass(frozen=True)
class ForecastRequest:
    region: RegionSpec
    cutoff: str


def parse_cutoff(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def validate_forecast_request(request: ForecastRequest) -> list[str]:
    errors: list[str] = []

    if request.region.kind not in VALID_REGION_KINDS:
        errors.append(
            f"region.kind must be one of {sorted(VALID_REGION_KINDS)}, "
            f"got: {request.region.kind}"
        )

    if not request.cutoff.strip():
        errors.append("cutoff must not be empty")
    else:
        try:
            parse_cutoff(request.cutoff)
        except ValueError:
            errors.append(
                f"cutoff must be an ISO 8601 datetime, got: {request.cutoff!r}"
            )

    return errors


@dataclass(frozen=True)
class CellForecast:
    cell: GridCell
    probability: float
    drivers: tuple[FeatureContribution, ...] = ()


@dataclass(frozen=True)
class Explanation:
    method: str
    units: str
    importance: tuple[FeatureContribution, ...]


@dataclass(frozen=True)
class ForecastWindow:
    start: datetime
    end: datetime
    hours: int = FORECAST_WINDOW_HOURS


@dataclass(frozen=True)
class CalibrationMetadata:
    method: str
    table: list[CalibrationBin]


@dataclass(frozen=True)
class ForecastResult:
    cells: list[CellForecast]
    model_version: str
    data_cutoff: datetime
    forecast_window: ForecastWindow
    calibration: CalibrationMetadata
    evidence: Evidence
    explanation: Explanation | None = None


def build_forecast_window(cutoff: datetime) -> ForecastWindow:
    return ForecastWindow(
        start=cutoff, end=cutoff + timedelta(hours=FORECAST_WINDOW_HOURS)
    )


def build_forecast_result(
    cells: list[CellForecast],
    region: NormalizedRegion,
    cutoff: datetime,
    calibration_table: list[CalibrationBin],
    inputs: dict[str, Any] | None = None,
    explanation: Explanation | None = None,
) -> ForecastResult:
    forecast_window = build_forecast_window(cutoff)

    query_parameters: dict[str, Any] = {
        "cutoff": cutoff.isoformat(),
        "forecast_window_hours": FORECAST_WINDOW_HOURS,
    }
    if inputs is not None:
        query_parameters["inputs"] = inputs

    evidence = build_evidence(
        dataset=f"wildfire_forecast:{MODEL_VERSION}",
        region=region,
        time_range=NormalizedTimeRange(
            start=forecast_window.start, end=forecast_window.end
        ),
        query_parameters=query_parameters,
    )

    return ForecastResult(
        cells=cells,
        model_version=MODEL_VERSION,
        data_cutoff=cutoff,
        forecast_window=forecast_window,
        calibration=CalibrationMetadata(
            method=CALIBRATION_METHOD, table=calibration_table
        ),
        evidence=evidence,
        explanation=explanation,
    )


def contribution_to_dict(entry: FeatureContribution) -> dict[str, Any]:
    return {"feature": entry.feature, "contribution": round(entry.contribution, 4)}


def cell_forecast_to_feature(cell_forecast: CellForecast) -> dict[str, Any]:
    feature = cell_to_feature(cell_forecast.cell)
    feature["properties"]["probability"] = cell_forecast.probability
    if cell_forecast.drivers:
        feature["properties"]["top_drivers"] = [
            contribution_to_dict(driver) for driver in cell_forecast.drivers
        ]

    return feature


def build_forecast_grid(cells: list[CellForecast]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [cell_forecast_to_feature(cell) for cell in cells],
    }


def forecast_result_to_dict(result: ForecastResult) -> dict[str, Any]:
    payload = {
        "grid": build_forecast_grid(result.cells),
        "model_version": result.model_version,
        "data_cutoff": result.data_cutoff.isoformat(),
        "forecast_window": {
            "start": result.forecast_window.start.isoformat(),
            "end": result.forecast_window.end.isoformat(),
            "hours": result.forecast_window.hours,
        },
        "calibration": {
            "method": result.calibration.method,
            "table": [asdict(entry) for entry in result.calibration.table],
        },
        "evidence": evidence_to_dict(result.evidence),
    }
    if result.explanation is not None:
        payload["explanation"] = {
            "method": result.explanation.method,
            "units": result.explanation.units,
            "importance": [
                contribution_to_dict(entry) for entry in result.explanation.importance
            ],
        }

    return payload
