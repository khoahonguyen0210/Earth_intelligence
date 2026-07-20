from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.harness import (
    SUPPORTED_MODELS,
    run_experiment_on_rows,
)

BENCHMARK_VERSION = "v1"


@dataclass(frozen=True)
class BenchmarkRow:
    model: str
    succeeded: bool
    pr_auc: float | None
    roc_auc: float | None
    brier_score: float | None
    log_loss: float | None
    training_time_seconds: float | None
    inference_time_seconds: float | None
    error: str | None


def run_baseline_benchmark(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    test_rows: list[DatasetRow],
    artifacts_root: Path = Path("ml/artifacts"),
    experiment_prefix: str = "final_baseline_benchmark_v1",
) -> list[BenchmarkRow]:
    """Runs every model in the locked ladder (Climatology, Logistic
    Regression, XGBoost, Calibrated XGBoost) through the Task 4.5 harness
    and returns one comparable row per model, including training/
    inference time -- the two metrics this task adds on top of Task 4.5's
    per-model artifacts."""
    rows: list[BenchmarkRow] = []

    for model_name in SUPPORTED_MODELS:
        result = run_experiment_on_rows(
            model_name,
            f"{experiment_prefix}_{model_name}",
            train_rows,
            validation_rows,
            test_rows,
            artifacts_root,
        )
        config = json.loads(result.paths.config.read_text(encoding="utf-8"))

        rows.append(
            BenchmarkRow(
                model=model_name,
                succeeded=result.succeeded,
                pr_auc=result.metrics.pr_auc if result.metrics else None,
                roc_auc=result.metrics.roc_auc if result.metrics else None,
                brier_score=result.metrics.brier_score if result.metrics else None,
                log_loss=result.metrics.log_loss if result.metrics else None,
                training_time_seconds=config.get("training_time_seconds"),
                inference_time_seconds=config.get("inference_time_seconds"),
                error=result.error,
            )
        )

    return rows


def save_benchmark_comparison(rows: list[BenchmarkRow], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": [asdict(row) for row in rows],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return output_path


def save_benchmark_table(rows: list[BenchmarkRow], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = (
        "model,succeeded,pr_auc,roc_auc,brier_score,log_loss,"
        "training_time_seconds,inference_time_seconds,error"
    )

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(header + "\n")

        for row in rows:
            error_text = (row.error or "").replace(",", ";")
            handle.write(
                f"{row.model},{row.succeeded},{row.pr_auc},{row.roc_auc},"
                f"{row.brier_score},{row.log_loss},{row.training_time_seconds},"
                f"{row.inference_time_seconds},{error_text}\n"
            )

    return output_path
