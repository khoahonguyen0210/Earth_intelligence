from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    predict_calibrated,
)
from ai_earth_intelligence_and_forecasting_engine.models.drift import (
    build_reference,
    save_reference,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    block_bootstrap,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    compute_metrics,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    ProductionModel,
    load_production_model,
    save_production_model,
    train_production_model,
)

LOCKED_TEST_SEASON = 2024
MIN_PR_AUC_GAIN = 0.01
MAX_BRIER_RATIO = 1.05
REGISTRY_FILE = "registry.json"
VERSIONS_DIR = "versions"


@dataclass(frozen=True)
class SeasonWindows:
    fit: tuple[int, ...]
    calibration: int
    gate: int


def season_windows(newest_season: int, first_season: int) -> SeasonWindows:
    if newest_season - first_season < 2:
        raise ValueError(
            f"need at least one fit season before {newest_season - 1}; "
            f"data starts in {first_season}"
        )
    return SeasonWindows(
        fit=tuple(range(first_season, newest_season - 1)),
        calibration=newest_season - 1,
        gate=newest_season,
    )


def season_of(row: DatasetRow) -> int:
    return row.cutoff.year


@dataclass(frozen=True)
class GateScore:
    pr_auc: float
    brier: float
    rows: int
    fires: int


def score_on(model: ProductionModel, rows: list[DatasetRow]) -> GateScore:
    metrics = compute_metrics(
        [row.target for row in rows], predict_calibrated(model.calibrated, rows)
    )
    return GateScore(
        pr_auc=metrics.pr_auc,
        brier=metrics.brier_score,
        rows=metrics.n_samples,
        fires=metrics.n_positive,
    )


@dataclass(frozen=True)
class Decision:
    promote: bool
    reason: str


def decide(candidate: GateScore, current: GateScore | None) -> Decision:
    if current is None:
        return Decision(True, "no current model")
    gain = candidate.pr_auc - current.pr_auc
    brier_ratio = candidate.brier / current.brier if current.brier else 1.0
    if gain < MIN_PR_AUC_GAIN:
        return Decision(False, f"PR-AUC gain {gain:+.4f} is below {MIN_PR_AUC_GAIN}")
    if brier_ratio > MAX_BRIER_RATIO:
        return Decision(False, f"Brier score worse by x{brier_ratio:.3f}")
    return Decision(True, f"PR-AUC {gain:+.4f}, Brier x{brier_ratio:.3f}")


def deploy(version_dir: Path, served_dir: Path) -> None:
    incoming = served_dir.parent / f".{served_dir.name}.incoming"
    previous = served_dir.parent / f".{served_dir.name}.previous"
    for leftover in (incoming, previous):
        if leftover.exists():
            shutil.rmtree(leftover)
    shutil.copytree(version_dir, incoming)
    if served_dir.exists():
        served_dir.rename(previous)
    incoming.rename(served_dir)
    if previous.exists():
        shutil.rmtree(previous)


class ModelRegistry:
    def __init__(self, root: Path):
        self.root = root
        self._path = root / REGISTRY_FILE
        if self._path.exists():
            self.state: dict[str, Any] = json.loads(
                self._path.read_text(encoding="utf-8")
            )
        else:
            self.state = {"current": None, "promotions": [], "runs": []}

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def version_dir(self, version: str) -> Path:
        return self.root / VERSIONS_DIR / version

    @property
    def current(self) -> str | None:
        current: str | None = self.state["current"]
        return current

    def add_version(
        self, version: str, model: ProductionModel, reference: dict[str, Any]
    ) -> Path:
        directory = self.version_dir(version)
        save_production_model(model, directory)
        save_reference(reference, directory)
        return directory

    def register_existing(self, version: str, model_dir: Path) -> None:
        shutil.copytree(model_dir, self.version_dir(version), dirs_exist_ok=True)
        self.state["current"] = version
        self.state["promotions"].append(
            {"version": version, "at": _now(), "reason": "registered existing model"}
        )
        self._save()

    def load_current(self) -> ProductionModel | None:
        if self.current is None:
            return None
        return load_production_model(self.version_dir(self.current))

    def promote(self, version: str, reason: str, served_dir: Path | None) -> None:
        if not self.version_dir(version).exists():
            raise ValueError(f"unknown version {version!r}")
        if served_dir is not None:
            deploy(self.version_dir(version), served_dir)
        self.state["current"] = version
        self.state["promotions"].append(
            {"version": version, "at": _now(), "reason": reason}
        )
        self._save()

    def rollback(self, served_dir: Path | None) -> str:
        promoted = [entry["version"] for entry in self.state["promotions"]]
        earlier = [version for version in promoted[:-1] if version != self.current]
        if not earlier:
            raise ValueError("no earlier promoted version to roll back to")
        target = earlier[-1]
        self.promote(target, f"rollback from {self.current}", served_dir)
        return target

    def record_run(self, run: dict[str, Any]) -> None:
        self.state["runs"].append(run)
        self._save()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bootstrap_gain(
    candidate: ProductionModel, current: ProductionModel, rows: list[DatasetRow]
) -> dict[str, float]:
    y = np.array([row.target for row in rows])
    groups = np.array([row.cutoff.isoformat() for row in rows])
    scores = {
        "candidate": np.array(predict_calibrated(candidate.calibrated, rows)),
        "current": np.array(predict_calibrated(current.calibrated, rows)),
    }
    _, difference = block_bootstrap(y, scores, groups, baseline="current")
    gain = difference["candidate"]
    return {
        "estimate": round(gain.estimate, 4),
        "low": round(gain.low, 4),
        "high": round(gain.high, 4),
    }


def run_retraining(
    rows: list[DatasetRow],
    newest_season: int,
    registry: ModelRegistry,
    served_dir: Path | None = None,
) -> dict[str, Any]:
    if newest_season == LOCKED_TEST_SEASON:
        raise ValueError(
            f"{LOCKED_TEST_SEASON} is the locked test season and can never "
            "decide a promotion"
        )
    seasons = sorted({season_of(row) for row in rows})
    if newest_season not in seasons:
        raise ValueError(f"no rows for season {newest_season}; have {seasons}")
    windows = season_windows(newest_season, seasons[0])

    fit_rows = [row for row in rows if season_of(row) in windows.fit]
    calibration_rows = [row for row in rows if season_of(row) == windows.calibration]
    gate_rows = [row for row in rows if season_of(row) == windows.gate]

    version = f"season{newest_season}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    candidate = train_production_model(fit_rows, calibration_rows, version)
    season_record = {**asdict(windows), "fit": list(windows.fit)}
    candidate.metadata["seasons"] = season_record
    current = registry.load_current()

    candidate_score = score_on(candidate, gate_rows)
    current_score = score_on(current, gate_rows) if current is not None else None
    decision = decide(candidate_score, current_score)

    registry.add_version(version, candidate, build_reference(fit_rows))
    run: dict[str, Any] = {
        "at": _now(),
        "candidate": version,
        "current": registry.current,
        "seasons": season_record,
        "candidate_score": asdict(candidate_score),
        "current_score": asdict(current_score) if current_score else None,
        "pr_auc_gain_interval": (
            _bootstrap_gain(candidate, current, gate_rows) if current else None
        ),
        "promoted": decision.promote,
        "reason": decision.reason,
    }
    if decision.promote:
        registry.promote(version, decision.reason, served_dir)
    registry.record_run(run)
    return run
