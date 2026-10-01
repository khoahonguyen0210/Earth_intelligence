"""Gated retraining: train a candidate on new data, keep it only if it
beats the model in service.

    python scripts/models/retrain.py --register-current      # once
    python scripts/models/retrain.py --season 2025 --deploy  # each new season
    python scripts/models/retrain.py --rollback --deploy
    python scripts/models/retrain.py --replay                 # backtest on history

`--season Y` needs season Y in the dataset; the locked 2024 test season
is refused as a gate. `--deploy` swaps the served model directory when a
candidate is promoted. `--replay` runs the loop over 2021-2023 in a
separate registry and never touches the served model.
"""

import argparse
import json
import shutil
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    ModelRegistry,
    run_retraining,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
SERVED_DIR = Path("ml/artifacts/production_model_v1")
REGISTRY_DIR = Path("ml/artifacts/model_registry")
REPLAY_REGISTRY_DIR = Path("ml/artifacts/model_registry_replay")
REPLAY_SEASONS = (2021, 2022, 2023)
REPLAY_REPORT = Path("data/processed/evaluation/retraining_replay_v1.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--season", type=int)
    action.add_argument("--register-current", action="store_true")
    action.add_argument("--rollback", action="store_true")
    action.add_argument("--replay", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    served = SERVED_DIR if args.deploy else None

    if args.register_current:
        registry = ModelRegistry(REGISTRY_DIR)
        registry.register_existing("v1", SERVED_DIR)
        print(f"registered {SERVED_DIR} as v1")
        return

    if args.rollback:
        print(f"rolled back to {ModelRegistry(REGISTRY_DIR).rollback(served)}")
        return

    rows = load_dataset(DATASET_PATH)

    if args.replay:
        if REPLAY_REGISTRY_DIR.exists():
            shutil.rmtree(REPLAY_REGISTRY_DIR)
        registry = ModelRegistry(REPLAY_REGISTRY_DIR)
        runs = [run_retraining(rows, season, registry) for season in REPLAY_SEASONS]
        report = {"runs": runs, "final_current": registry.current}
        REPLAY_REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPLAY_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"saved -> {REPLAY_REPORT}")
        return

    run = run_retraining(rows, args.season, ModelRegistry(REGISTRY_DIR), served)
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
