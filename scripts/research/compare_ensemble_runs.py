import argparse
import json
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.earth2.ensemble import (
    agreement,
    load_ensemble,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    FEATURES,
    load_cutoff_forecast,
)

REFERENCE_RUN = "gpus1_batch1_1"
BATCH_GAIN = 1.10
TWO_GPU_TIME_SHARE = 0.55


def load_run(directory: Path) -> dict:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    ensemble_path = directory / "ensemble.npz"
    summary["ensemble"] = (
        load_ensemble(ensemble_path) if ensemble_path.exists() else None
    )
    return summary


def compare_members(run, reference) -> dict:
    results = [
        agreement(run.features[name], reference.features[name]) for name in FEATURES
    ]
    return {
        "identical": all(item["identical"] for item in results),
        "within_tolerance": all(item["within_tolerance"] for item in results),
        "largest_error_over_limit": max(
            item["largest_error_over_limit"] for item in results
        ),
    }


def compare_control(run, forecast) -> dict:
    position = int(np.flatnonzero(run.members == 0)[0])
    results = [
        agreement(run.features[name][position], forecast.features[name])
        for name in FEATURES
    ]
    return {
        "identical": all(item["identical"] for item in results),
        "within_tolerance": all(item["within_tolerance"] for item in results),
    }


def runs_of(runs: dict, gpus: int, batch: int) -> list[dict]:
    return [
        run
        for run in runs.values()
        if run["gpus"] == gpus and run["batch_size"] == batch
    ]


def batching_kept(runs: dict, batch: int, checks: dict) -> bool:
    tried = runs_of(runs, 1, batch)
    baselines = runs_of(runs, 1, 1)
    if not tried or not baselines:
        return False
    for run in tried:
        if not run["completed"] or not checks[run["name"]]["within_tolerance"]:
            return False
        for baseline in baselines:
            gain = BATCH_GAIN * baseline["warm_member_steps_per_second"]
            if run["warm_member_steps_per_second"] < gain:
                return False
    return True


def two_gpus_kept(runs: dict, checks: dict) -> bool:
    tried = runs_of(runs, 2, 1)
    baselines = runs_of(runs, 1, 1)
    if not tried or not baselines:
        return False
    for run in tried:
        if not run["completed"] or not checks[run["name"]]["identical"]:
            return False
        for baseline in baselines:
            limit = TWO_GPU_TIME_SHARE * baseline["forecast_wall_seconds"]
            if run["forecast_wall_seconds"] > limit:
                return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path)
    parser.add_argument("--forecast", type=Path)
    arguments = parser.parse_args()

    runs = {}
    for path in sorted(arguments.runs.glob("*/summary.json")):
        run = load_run(path.parent)
        run["name"] = path.parent.name
        runs[run["name"]] = run
    if REFERENCE_RUN not in runs or runs[REFERENCE_RUN]["ensemble"] is None:
        raise SystemExit(f"{REFERENCE_RUN} is missing or did not finish")
    reference = runs[REFERENCE_RUN]["ensemble"]
    forecast = load_cutoff_forecast(arguments.forecast) if arguments.forecast else None

    checks = {}
    rows = []
    for name, run in runs.items():
        ensemble = run["ensemble"]
        check = compare_members(ensemble, reference) if ensemble else {}
        checks[name] = check
        activity = [worker.get("gpu_activity", {}) for worker in run["workers"]]
        row = {
            "run": name,
            "gpus": run["gpus"],
            "batch_size": run["batch_size"],
            "completed": run["completed"],
            "forecast_wall_seconds": run.get("forecast_wall_seconds"),
            "members_per_minute": run.get("members_per_minute"),
            "warm_member_steps_per_second": run.get("warm_member_steps_per_second"),
            "peak_memory_gb": run["peak_memory_gb"],
            "model_memory_gb": [w.get("model_memory_gb") for w in run["workers"]],
            "mean_utilization_percent": [
                item.get("mean_utilization_percent") for item in activity
            ],
            "mean_sm_clock_mhz": [item.get("mean_sm_clock_mhz") for item in activity],
            "max_temperature_c": [item.get("max_temperature_c") for item in activity],
            "mean_power_w": [item.get("mean_power_w") for item in activity],
            "errors": [w.get("error") for w in run["workers"] if w.get("error")],
            "hdw_spread_by_lead": run.get("hdw_spread_by_lead"),
            **{f"members_{key}": value for key, value in check.items()},
        }
        if ensemble is not None and forecast is not None:
            control = compare_control(ensemble, forecast)
            row.update({f"control_{key}": value for key, value in control.items()})
        rows.append(row)

    decisions = {
        f"batch_{batch}": batching_kept(runs, batch, checks)
        for batch in sorted({run["batch_size"] for run in runs.values()} - {1})
    }
    decisions["two_gpus"] = two_gpus_kept(runs, checks)
    output = {"runs": rows, "kept": decisions}
    (arguments.runs / "comparison.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
