from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isnan
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    ClassificationMetrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    NUMERIC_FEATURE_COLUMNS,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    evaluate_xgboost,
)

ABLATION_VERSION = "v1"

# The same NUMERIC_FEATURE_COLUMNS (preprocessing.py) split into the two
# feature groups run_weather_ablation compares. Geography columns
# (elevation_m, slope_deg, land_cover_class) are deliberately excluded
# from both variants -- that comparison belongs to run_geography_ablation,
# not this one.
FIRE_HISTORY_FEATURE_COLUMNS: tuple[str, ...] = (
    "previous_24h_count",
    "previous_72h_count",
    "previous_7d_count",
    "previous_30d_count",
    "neighboring_previous_24h_count",
)

WEATHER_FEATURE_COLUMNS: tuple[str, ...] = (
    "temperature_2m",
    "total_precipitation",
    "u_wind_10m",
    "v_wind_10m",
    "relative_humidity",
)

FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS: tuple[str, ...] = (
    FIRE_HISTORY_FEATURE_COLUMNS + WEATHER_FEATURE_COLUMNS
)

# run_geography_ablation adds these on top of fire-history+weather: the
# two static, numeric geography columns plus (via include_land_cover=True
# below) the ESA WorldCover land-cover one-hot. Together with
# fire-history and weather, this is the complete locked feature set --
# the same columns as NUMERIC_FEATURE_COLUMNS, in the same order.
GEOGRAPHY_FEATURE_COLUMNS: tuple[str, ...] = (
    "elevation_m",
    "slope_deg",
)


@dataclass(frozen=True)
class AblationVariant:
    name: str
    feature_columns: tuple[str, ...]
    include_land_cover: bool
    succeeded: bool
    metrics: ClassificationMetrics | None
    error: str | None


@dataclass(frozen=True)
class AblationResult:
    baseline: AblationVariant
    candidate: AblationVariant
    pr_auc_delta: float | None
    roc_auc_delta: float | None
    brier_score_delta: float | None
    log_loss_delta: float | None


def _run_variant(
    name: str,
    feature_columns: tuple[str, ...],
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    include_land_cover: bool = False,
) -> AblationVariant:
    try:
        _result, _predictions, metrics = evaluate_xgboost(
            train_rows,
            validation_rows,
            test_rows,
            feature_columns=feature_columns,
            include_land_cover=include_land_cover,
        )
    except ValueError as error:
        return AblationVariant(
            name=name,
            feature_columns=feature_columns,
            include_land_cover=include_land_cover,
            succeeded=False,
            metrics=None,
            error=str(error),
        )

    return AblationVariant(
        name=name,
        feature_columns=feature_columns,
        include_land_cover=include_land_cover,
        succeeded=True,
        metrics=metrics,
        error=None,
    )


def _delta(
    baseline: ClassificationMetrics | None,
    candidate: ClassificationMetrics | None,
    field: str,
) -> float | None:
    if baseline is None or candidate is None:
        return None

    baseline_value = getattr(baseline, field)
    candidate_value = getattr(candidate, field)

    if isnan(baseline_value) or isnan(candidate_value):
        return None

    return candidate_value - baseline_value


def run_weather_ablation(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
) -> AblationResult:
    """Fire-history-only vs fire-history+weather, with the test period
    and the XGBoost model protocol (BASE_CONFIG, same early-stopping
    rule) held fixed -- the only difference between the two runs is
    which feature columns are fed into the model."""
    baseline = _run_variant(
        "fire_history_only",
        FIRE_HISTORY_FEATURE_COLUMNS,
        train_rows,
        validation_rows,
        test_rows,
    )
    candidate = _run_variant(
        "fire_history_plus_weather",
        FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS,
        train_rows,
        validation_rows,
        test_rows,
    )

    return AblationResult(
        baseline=baseline,
        candidate=candidate,
        pr_auc_delta=_delta(baseline.metrics, candidate.metrics, "pr_auc"),
        roc_auc_delta=_delta(baseline.metrics, candidate.metrics, "roc_auc"),
        brier_score_delta=_delta(baseline.metrics, candidate.metrics, "brier_score"),
        log_loss_delta=_delta(baseline.metrics, candidate.metrics, "log_loss"),
    )


def run_geography_ablation(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
) -> AblationResult:
    """Fire-history+weather vs fire-history+weather+geography (the
    complete locked feature set -- NUMERIC_FEATURE_COLUMNS plus the ESA
    WorldCover land-cover one-hot), with the same XGBoost protocol and
    test period held fixed as run_weather_ablation."""
    baseline = _run_variant(
        "fire_history_plus_weather",
        FIRE_HISTORY_PLUS_WEATHER_FEATURE_COLUMNS,
        train_rows,
        validation_rows,
        test_rows,
        include_land_cover=False,
    )
    candidate = _run_variant(
        "fire_history_plus_weather_plus_geography",
        NUMERIC_FEATURE_COLUMNS,
        train_rows,
        validation_rows,
        test_rows,
        include_land_cover=True,
    )

    return AblationResult(
        baseline=baseline,
        candidate=candidate,
        pr_auc_delta=_delta(baseline.metrics, candidate.metrics, "pr_auc"),
        roc_auc_delta=_delta(baseline.metrics, candidate.metrics, "roc_auc"),
        brier_score_delta=_delta(baseline.metrics, candidate.metrics, "brier_score"),
        log_loss_delta=_delta(baseline.metrics, candidate.metrics, "log_loss"),
    )


def _variant_to_dict(variant: AblationVariant) -> dict:
    payload = asdict(variant)
    payload["metrics"] = asdict(variant.metrics) if variant.metrics else None
    return payload


def save_ablation_result(result: AblationResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "ablation_version": ABLATION_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": _variant_to_dict(result.baseline),
        "candidate": _variant_to_dict(result.candidate),
        "deltas": {
            "pr_auc": result.pr_auc_delta,
            "roc_auc": result.roc_auc_delta,
            "brier_score": result.brier_score_delta,
            "log_loss": result.log_loss_delta,
        },
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return output_path
