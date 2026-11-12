import argparse
import csv
import gzip
import json
import pickle
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    firms_covered_days,
    load_firms_history,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.e7 import (
    BASE_FEATURES,
    E7_FEATURES,
    E7_VERSION,
    FORECAST_MODEL,
    NO_FORECAST_MODEL,
    build_lead_rows,
    cell_forecasts,
    e7_split,
    lead_fire_tiles,
    lead_scores,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.portable import export_model
from ai_earth_intelligence_and_forecasting_engine.earth2.store import load_forecast_set
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    SPLIT_YEARS,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.historical_dataset import (
    ObservationIndex,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    build_calibration_table,
    plot_reliability_diagram,
    save_calibration_table,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    BOOTSTRAP_SAMPLES,
    BOOTSTRAP_SEED,
    block_bootstrap,
)
from ai_earth_intelligence_and_forecasting_engine.models.metrics import (
    compute_metrics,
    metrics_to_dict,
)
from ai_earth_intelligence_and_forecasting_engine.models.production_model import (
    load_production_model,
)
from ai_earth_intelligence_and_forecasting_engine.models.xgboost_model import (
    BASE_CONFIG,
)

DATASET_PATHS = (
    Path("data/processed/historical_dataset_v1.csv"),
    Path("data/processed/historical_dataset_2025.csv"),
)
FIRMS_DIRS = (Path("data/raw/firms/history"), Path("data/raw/firms/e7_labels"))
FORECAST_DIR = Path("ml/artifacts/e7_forecasts")
PRODUCTION_MODEL_DIR = Path("ml/artifacts/production_model_v1")
OUTPUT_DIR = Path("ml/artifacts/e7_multi_day_v1")
PROBABILITY_SCORES = (
    "climatology",
    "production_model",
    NO_FORECAST_MODEL,
    FORECAST_MODEL,
)


def _interval(entry) -> dict[str, float]:
    return {
        "estimate": round(entry.estimate, 4),
        "low": round(entry.low, 4),
        "high": round(entry.high, 4),
    }


def load_base_rows(cutoffs: set[datetime]):
    rows = []
    for path in DATASET_PATHS:
        rows += [
            row
            for row in load_dataset(path)
            if e7_split(row.cutoff) is not None and row.cutoff in cutoffs
        ]
    return rows


def fire_tiles_by_lead(cutoffs: list[datetime]) -> dict[int, dict[datetime, set[str]]]:
    covered = set().union(*(firms_covered_days(path) for path in FIRMS_DIRS))
    horizon = timedelta(days=LEAD_DAYS[-1])
    for cutoff in cutoffs:
        day, last = cutoff.date(), (cutoff + horizon).date()
        while day <= last:
            if day not in covered:
                raise SystemExit(
                    f"no FIRMS data for {day}; run "
                    "scripts/research/download_e7_fire_labels.py first"
                )
            day += timedelta(days=1)

    result: dict[int, dict[datetime, set[str]]] = {lead: {} for lead in LEAD_DAYS}
    for year in sorted({cutoff.year for cutoff in cutoffs}):
        in_year = [cutoff for cutoff in cutoffs if cutoff.year == year]
        start, end = in_year[0], in_year[-1] + horizon
        observations = []
        for path in FIRMS_DIRS:
            observations += load_firms_history(path, start, end)
        index = ObservationIndex(observations)
        for cutoff in in_year:
            window = index.between(cutoff, cutoff + horizon)
            for lead in LEAD_DAYS:
                result[lead][cutoff] = lead_fire_tiles(window, cutoff, lead)
    return result


def evaluate_lead(lead, rows, production_model):
    train = [row for row in rows if row.split == "train"]
    validation = [row for row in rows if row.split == "validation"]
    test = [row for row in rows if row.split == "test"]
    started = time.perf_counter()
    scores, models = lead_scores(train, validation, test, production_model)
    y = np.array([row.target for row in test])
    groups = np.array([row.cutoff.isoformat() for row in test])
    report = {
        "lead_day": lead,
        "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "fires": {
            "train": sum(row.target for row in train),
            "validation": sum(row.target for row in validation),
            "test": int(y.sum()),
        },
        "point": {
            name: metrics_to_dict(compute_metrics(y.tolist(), values.tolist()))
            for name, values in scores.items()
            if name in PROBABILITY_SCORES
        },
    }
    probabilities = {
        name: values for name, values in scores.items() if name in PROBABILITY_SCORES
    }
    runs = [
        ("pr_auc", scores, NO_FORECAST_MODEL),
        ("roc_auc", scores, NO_FORECAST_MODEL),
        ("pr_auc", scores, "persistence_24h"),
        ("brier", probabilities, NO_FORECAST_MODEL),
        ("log_loss", probabilities, NO_FORECAST_MODEL),
    ]
    for metric_name, selected, baseline in runs:
        metric, difference = block_bootstrap(
            y, selected, groups, baseline=baseline, metric_name=metric_name
        )
        report.setdefault(metric_name, {n: _interval(i) for n, i in metric.items()})
        report[f"{metric_name}_minus_{baseline}"] = {
            name: _interval(item) for name, item in difference.items()
        }
    report["seconds"] = round(time.perf_counter() - started, 1)
    return report, scores, models, test


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecasts", type=Path, default=FORECAST_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    arguments = parser.parse_args()
    output_dir = arguments.output
    started = time.perf_counter()

    forecasts = load_forecast_set(arguments.forecasts)
    cells = build_california_grid()
    cell_index = {cell.tile_id: index for index, cell in enumerate(cells)}
    cutoffs = [cutoff for cutoff in forecasts.cutoffs if e7_split(cutoff)]
    base_rows = load_base_rows(set(cutoffs))
    fire_tiles = fire_tiles_by_lead(cutoffs)
    mismatched = sum(
        row.target != int(row.tile_id in fire_tiles[1][row.cutoff])
        for row in base_rows
    )

    served = (
        load_production_model(PRODUCTION_MODEL_DIR).calibrated
        if PRODUCTION_MODEL_DIR.exists()
        else None
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "models").mkdir(exist_ok=True)
    reports = []
    with gzip.open(output_dir / "predictions.csv.gz", "wt", newline="") as handle:
        writer = None
        for lead in LEAD_DAYS:
            rows = build_lead_rows(
                base_rows,
                lead,
                fire_tiles[lead],
                cell_forecasts(forecasts, cells, lead),
                cell_index,
            )
            report, scores, models, test = evaluate_lead(lead, rows, served)
            reports.append(report)
            print(json.dumps({k: report[k] for k in ("lead_day", "rows", "fires")}))

            model_path = output_dir / "models" / f"lead_{lead}"
            with model_path.with_suffix(".pkl").open("wb") as model_file:
                pickle.dump(models[FORECAST_MODEL], model_file)
            model_path.with_suffix(".json").write_text(
                json.dumps(export_model(models[FORECAST_MODEL])), "utf-8"
            )
            table = build_calibration_table(
                [row.target for row in test], scores[FORECAST_MODEL].tolist()
            )
            save_calibration_table(table, output_dir / f"calibration_lead_{lead}.csv")
            plot_reliability_diagram(
                table, output_dir / "plots" / f"reliability_lead_{lead}.png"
            )

            names = sorted(scores)
            if writer is None:
                writer = csv.writer(handle)
                writer.writerow(["tile_id", "cutoff", "lead_day", "target", *names])
            for position, row in enumerate(test):
                values = [round(float(scores[name][position]), 6) for name in names]
                writer.writerow(
                    [row.tile_id, row.cutoff.isoformat(), lead, row.target, *values]
                )

    config = {
        "experiment_id": E7_VERSION,
        "forecast_model": forecasts.metadata.get("model"),
        "index_version": forecasts.metadata.get("index_version"),
        "forecast_metadata": {
            key: value
            for key, value in forecasts.metadata.items()
            if key not in ("seconds", "approximate")
        },
        "cutoffs": len(cutoffs),
        "split_years": SPLIT_YEARS,
        "lead_days": list(LEAD_DAYS),
        "features": {
            NO_FORECAST_MODEL: [*BASE_FEATURES, "land_cover_one_hot"],
            FORECAST_MODEL: [*E7_FEATURES, "land_cover_one_hot"],
        },
        "xgboost": BASE_CONFIG,
        "calibration": "isotonic on the validation split",
        "production_model": str(PRODUCTION_MODEL_DIR) if served else None,
        "bootstrap": {
            "groups": "cutoff date",
            "samples": BOOTSTRAP_SAMPLES,
            "seed": BOOTSTRAP_SEED,
        },
    }
    metrics = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(time.perf_counter() - started, 1),
        "day_1_label_mismatches": int(mismatched),
        "leads": reports,
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2), "utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), "utf-8")
    (output_dir / "README.md").write_text(
        "# E7 multi-day risk\n\nSee docs/multi-day-risk.md. Created by "
        "scripts/research/run_e7.py.\n",
        "utf-8",
    )
    print(json.dumps(metrics["leads"], indent=2)[:4000])


if __name__ == "__main__":
    main()
