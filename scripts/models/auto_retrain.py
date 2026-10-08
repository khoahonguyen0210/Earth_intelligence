import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.auto_retrain import (
    Steps,
    latest_complete_season,
    pending_seasons,
    run_pending,
)
from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    ModelRegistry,
    run_retraining,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
SEASON_DATASETS = "historical_dataset_20*.csv"
SERVED_DIR = Path("ml/artifacts/production_model_v1")
REGISTRY_DIR = Path("ml/artifacts/model_registry")
LOG_PATH = REGISTRY_DIR / "auto_retrain_log.jsonl"


def run_script(script: str, year: int) -> None:
    subprocess.run(
        [sys.executable, script, "--year", str(year)], check=True, text=True
    )


def download_season(year: int) -> None:
    run_script("scripts/data/download_firms_history.py", year)
    run_script("scripts/data/download_era5_history.py", year)


def build_if_missing(year: int) -> None:
    if not Path(f"data/processed/historical_dataset_{year}.csv").exists():
        run_script("scripts/forecast/build_historical_dataset.py", year)


def load_all_rows():
    rows = load_dataset(DATASET_PATH)
    for path in sorted(DATASET_PATH.parent.glob(SEASON_DATASETS)):
        rows.extend(load_dataset(path))
    return rows


def main() -> None:
    registry = ModelRegistry(REGISTRY_DIR)
    if registry.current is None:
        registry.register_existing("v1", SERVED_DIR)

    today = date.today()
    pending = pending_seasons(registry, today)
    print(f"latest complete season: {latest_complete_season(today)}; pending: {pending}")
    if not pending:
        print("up to date, nothing to do")
        return

    def retrain(season: int) -> dict:
        return run_retraining(load_all_rows(), season, registry, SERVED_DIR)

    steps = Steps(download=download_season, build=build_if_missing, retrain=retrain)
    results = run_pending(registry, today, steps)

    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(
                json.dumps({"logged_at": datetime.now(timezone.utc).isoformat(), **result})
                + "\n"
            )
    for result in results:
        outcome = "promoted" if result["promoted"] else "kept current model"
        print(f"season {result['seasons']['gate']}: {outcome} ({result['reason']})")


if __name__ == "__main__":
    main()
