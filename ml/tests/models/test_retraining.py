from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    load_production_model,
)
from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    MIN_PR_AUC_GAIN,
    GateScore,
    ModelRegistry,
    decide,
    deploy,
    run_retraining,
    season_windows,
)


def _row(season: int, index: int, target: int, fires: int) -> DatasetRow:
    return DatasetRow(
        tile_id=f"CA_{index:04d}_0001",
        cutoff=datetime(season, 8, 1 + index % 4, 10, tzinfo=timezone.utc),
        split="train",
        target=target,
        previous_24h_count=fires,
        previous_72h_count=fires,
        previous_7d_count=fires + index % 3,
        previous_30d_count=fires + index % 5,
        neighboring_previous_24h_count=index % 2,
        temperature_2m=290.0 + index % 7,
        total_precipitation=0.001 * (index % 4),
        u_wind_10m=float(index % 3),
        v_wind_10m=-float(index % 2),
        relative_humidity=30.0 + index % 9,
        elevation_m=100.0 * (index % 6),
        slope_deg=float(index % 8),
        land_cover_class=(10, 30, 60)[index % 3],
    )


def _season(season: int) -> list[DatasetRow]:
    rows = []
    for index in range(80):
        burning = index % 3 == 0
        target = 1 if burning and index % 9 != 0 else int(index % 17 == 0)
        rows.append(_row(season, index, target, 40 if burning else 0))
    return rows


ROWS = [row for season in (2019, 2020, 2021, 2022) for row in _season(season)]


def test_windows_expand_and_keep_the_gate_season_unseen():
    windows = season_windows(2023, 2019)

    assert windows.fit == (2019, 2020, 2021)
    assert windows.calibration == 2022
    assert windows.gate == 2023
    with pytest.raises(ValueError, match="fit season"):
        season_windows(2020, 2019)


def test_decide_promotes_only_a_clear_improvement():
    current = GateScore(pr_auc=0.40, brier=0.0020, rows=100, fires=5)

    assert decide(GateScore(0.40 + MIN_PR_AUC_GAIN, 0.0020, 100, 5), current).promote
    small = decide(GateScore(0.405, 0.0020, 100, 5), current)
    assert not small.promote and "below" in small.reason
    worse_calibration = decide(GateScore(0.45, 0.0030, 100, 5), current)
    assert not worse_calibration.promote and "Brier" in worse_calibration.reason
    assert decide(GateScore(0.1, 0.01, 100, 5), None).promote


def test_the_locked_test_season_can_never_decide_a_promotion(tmp_path):
    with pytest.raises(ValueError, match="locked test season"):
        run_retraining(ROWS, 2024, ModelRegistry(tmp_path / "registry"))


def test_a_season_without_rows_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no rows for season 2023"):
        run_retraining(ROWS, 2023, ModelRegistry(tmp_path / "registry"))


def test_first_run_promotes_and_deploys_then_the_log_records_both_runs(tmp_path):
    registry = ModelRegistry(tmp_path / "registry")
    served = tmp_path / "served"

    first = run_retraining(ROWS, 2021, registry, served)
    second = run_retraining(ROWS, 2022, registry, served)

    assert first["promoted"] and first["reason"] == "no current model"
    assert first["seasons"] == {"fit": [2019], "calibration": 2020, "gate": 2021}
    assert second["current"] in (first["candidate"], second["candidate"])
    assert second["pr_auc_gain_interval"] is not None

    reloaded = ModelRegistry(tmp_path / "registry")
    assert [run["candidate"] for run in reloaded.state["runs"]] == [
        first["candidate"],
        second["candidate"],
    ]
    served_version = load_production_model(served).metadata["model_version"]
    assert served_version == reloaded.current
    assert (served / "feature_reference.json").is_file()


def test_rejected_candidates_are_kept_for_audit(tmp_path, monkeypatch):
    registry = ModelRegistry(tmp_path / "registry")
    run_retraining(ROWS, 2021, registry)
    current = registry.current

    from ai_earth_intelligence_and_forecasting_engine.models import retraining

    monkeypatch.setattr(
        retraining, "decide", lambda candidate, current: retraining.Decision(False, "x")
    )
    rejected = run_retraining(ROWS, 2022, registry)

    assert not rejected["promoted"]
    assert registry.current == current
    assert registry.version_dir(rejected["candidate"]).is_dir()


def test_rollback_restores_the_previous_promoted_version(tmp_path, monkeypatch):
    registry = ModelRegistry(tmp_path / "registry")
    served = tmp_path / "served"
    from ai_earth_intelligence_and_forecasting_engine.models import retraining

    monkeypatch.setattr(
        retraining, "decide", lambda candidate, current: retraining.Decision(True, "x")
    )
    first = run_retraining(ROWS, 2021, registry, served)
    second = run_retraining(ROWS, 2022, registry, served)

    restored = registry.rollback(served)

    assert restored == first["candidate"]
    assert registry.current == first["candidate"]
    assert load_production_model(served).metadata["model_version"] == restored
    assert registry.state["promotions"][-1]["reason"] == (
        f"rollback from {second['candidate']}"
    )


def test_rollback_with_nothing_earlier_is_refused(tmp_path):
    registry = ModelRegistry(tmp_path / "registry")
    run_retraining(ROWS, 2021, registry)

    with pytest.raises(ValueError, match="no earlier"):
        registry.rollback(None)


def test_deploy_replaces_the_served_directory_completely(tmp_path):
    version = tmp_path / "version"
    version.mkdir()
    (version / "model.pkl").write_text("new", encoding="utf-8")
    served = tmp_path / "served"
    served.mkdir()
    (served / "model.pkl").write_text("old", encoding="utf-8")
    (served / "stale.txt").write_text("gone", encoding="utf-8")

    deploy(version, served)

    assert (served / "model.pkl").read_text(encoding="utf-8") == "new"
    assert not (served / "stale.txt").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["served", "version"]


def test_registering_an_existing_model_makes_it_current(tmp_path):
    registry = ModelRegistry(tmp_path / "registry")
    run_retraining(ROWS, 2021, registry, tmp_path / "served")

    fresh = ModelRegistry(tmp_path / "other")
    fresh.register_existing("v1", tmp_path / "served")

    assert fresh.current == "v1"
    assert fresh.load_current() is not None
    saved = json.loads((tmp_path / "other" / "registry.json").read_text())
    assert saved["promotions"][0]["reason"] == "registered existing model"
