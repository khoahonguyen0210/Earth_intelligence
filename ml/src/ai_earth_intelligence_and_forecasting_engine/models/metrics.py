from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


@dataclass(frozen=True)
class ClassificationMetrics:
    """The locked primary metrics (project-context/PROJECT_BIBLE.md SS6):
    PR-AUC, ROC-AUC, Brier score, log loss. Accuracy is deliberately not
    included -- it is explicitly not the primary metric for this project.
    """

    pr_auc: float
    roc_auc: float
    brier_score: float
    log_loss: float
    n_samples: int
    n_positive: int
    positive_rate: float


def compute_metrics(
    y_true: list[int], y_pred_proba: list[float]
) -> ClassificationMetrics:
    if len(y_true) != len(y_pred_proba):
        raise ValueError("y_true and y_pred_proba must be the same length")

    if not y_true:
        raise ValueError("cannot compute metrics on an empty dataset")

    n_positive = sum(y_true)

    if 0 < n_positive < len(y_true):
        pr_auc = float(average_precision_score(y_true, y_pred_proba))
        roc_auc = float(roc_auc_score(y_true, y_pred_proba))
    else:
        # PR-AUC/ROC-AUC are undefined when only one class is present.
        pr_auc = float("nan")
        roc_auc = float("nan")

    return ClassificationMetrics(
        pr_auc=pr_auc,
        roc_auc=roc_auc,
        brier_score=float(brier_score_loss(y_true, y_pred_proba)),
        log_loss=float(log_loss(y_true, y_pred_proba, labels=[0, 1])),
        n_samples=len(y_true),
        n_positive=n_positive,
        positive_rate=n_positive / len(y_true),
    )


def metrics_to_dict(metrics: ClassificationMetrics) -> dict[str, Any]:
    return asdict(metrics)


def save_metrics(metrics: ClassificationMetrics, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics_to_dict(metrics), indent=2), encoding="utf-8"
    )

    return output_path
