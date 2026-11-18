import argparse
import json
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    load_cutoff_forecast,
)

ABSOLUTE_TOLERANCE = 0.01
RELATIVE_TOLERANCE = 0.001
CRITERIA = {
    "overlap_loading": {
        "stage": "total",
        "minimum_seconds": 3.0,
        "features": "identical",
    },
    "cudnn_benchmark": {
        "stage": "model_forward",
        "minimum_share": 0.10,
        "features": "tolerance",
    },
    "half_precision": {
        "stage": "model_forward",
        "minimum_share": 0.20,
        "features": "tolerance",
    },
    "larger_blocks": {
        "stage": "model_forward",
        "minimum_share": 0.05,
        "features": "identical",
        "maximum_peak_gb": 14.0,
    },
    "lean_imports": {
        "stage": "imports",
        "minimum_share": 0.50,
        "minimum_total_seconds": 15.0,
        "features": "identical",
    },
}


def load_run(directory: Path) -> dict:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    stages = {row["stage"]: row["seconds"] for row in summary["stages"]}
    stages["total"] = summary["total_seconds"]
    forecast = load_cutoff_forecast(next(directory.glob("forecast_*.npz")))
    return {"summary": summary, "stages": stages, "features": forecast.features}


def compare_features(features: dict, baseline: dict) -> dict:
    identical = True
    within = True
    largest = 0.0
    for name, reference in baseline.items():
        values = features[name]
        same_missing = np.array_equal(np.isnan(values), np.isnan(reference))
        present = ~np.isnan(reference)
        difference = np.abs(values[present] - reference[present])
        limit = ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * np.abs(reference[present])
        identical &= same_missing and bool(np.all(difference == 0))
        within &= same_missing and bool(np.all(difference <= limit))
        if difference.size:
            largest = max(largest, float(np.max(difference / limit)))
    return {
        "identical": identical,
        "within_tolerance": within,
        "largest_error_over_limit": round(largest, 4),
    }


def change_name(run_name: str) -> str:
    stem, _, number = run_name.rpartition("_")
    return stem if number.isdigit() else run_name


def meets(name: str, run: dict, baseline: dict, features: dict) -> bool:
    rule = CRITERIA[change_name(name)]
    stage = rule["stage"]
    saved = baseline["stages"][stage] - run["stages"][stage]
    total_saved = baseline["stages"]["total"] - run["stages"]["total"]
    if total_saved < rule.get("minimum_total_seconds", float("-inf")):
        return False
    if "minimum_seconds" in rule and saved < rule["minimum_seconds"]:
        return False
    if "minimum_share" in rule:
        if saved < rule["minimum_share"] * baseline["stages"][stage]:
            return False
    if "maximum_peak_gb" in rule:
        if run["summary"]["peak_memory_gb"] > rule["maximum_peak_gb"]:
            return False
    key = "identical" if rule["features"] == "identical" else "within_tolerance"
    return bool(features[key])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path)
    arguments = parser.parse_args()

    runs = {
        path.parent.name: load_run(path.parent)
        for path in sorted(arguments.runs.glob("*/summary.json"))
    }
    baselines = sorted(name for name in runs if name.startswith("baseline"))
    if not baselines:
        raise SystemExit("no baseline runs found")
    reference = runs[baselines[0]]

    rows = []
    for name, run in runs.items():
        features = compare_features(run["features"], reference["features"])
        row = {
            "run": name,
            "total_seconds": run["stages"]["total"],
            "model_load": run["stages"].get("model_load"),
            "imports": run["stages"].get("imports"),
            "data_loading": run["stages"].get("data_loading"),
            "model_forward": run["stages"].get("model_forward"),
            "peak_memory_gb": run["summary"]["peak_memory_gb"],
            **features,
        }
        if change_name(name) in CRITERIA:
            row["kept"] = all(
                meets(name, run, runs[baseline], features) for baseline in baselines
            )
        rows.append(row)

    output = arguments.runs / "comparison.json"
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    columns = list(dict.fromkeys(key for row in rows for key in row))
    print("| " + " | ".join(columns) + " |")
    print("|" + "---|" * len(columns))
    for row in rows:
        print("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")


if __name__ == "__main__":
    main()
