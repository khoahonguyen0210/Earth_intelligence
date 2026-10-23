import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
    load_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.models.climatology import (
    fit_climatology,
    predict_climatology,
)
from ai_earth_intelligence_and_forecasting_engine.models.evaluation import (
    BOOTSTRAP_SAMPLES,
    BOOTSTRAP_SEED,
    block_bootstrap,
)
from ai_earth_intelligence_and_forecasting_engine.research.fire_weather import (
    INDEX_VERSION,
    complete_weather,
    local_percentile,
    surface_index_components,
)

DATASET_PATH = Path("data/processed/historical_dataset_v1.csv")
SEASON_2025_PATH = Path("data/processed/historical_dataset_2025.csv")
OUTPUT_DIR = Path("ml/artifacts/earth2_index_validation")


def _interval(entry) -> dict[str, float]:
    return {
        "estimate": round(entry.estimate, 4),
        "low": round(entry.low, 4),
        "high": round(entry.high, 4),
    }


def _evaluate(
    period: str,
    rows: list[DatasetRow],
    climatology,
    history: tuple[list[str], np.ndarray],
) -> dict:
    components = surface_index_components(rows)
    components["surface_hdw_local_percentile"] = local_percentile(
        history[0],
        history[1],
        [row.tile_id for row in rows],
        components["surface_hdw"],
    )
    keep = complete_weather(components)
    kept = [row for row, flag in zip(rows, keep) if flag]

    y = np.array([row.target for row in kept])
    groups = np.array([row.cutoff.isoformat() for row in kept])
    scores = {
        "climatology": np.array(predict_climatology(climatology, kept)),
        **{name: values[keep] for name, values in components.items()},
    }

    report: dict = {
        "period": period,
        "rows": len(kept),
        "rows_without_weather": int((~keep).sum()),
        "fires": int(y.sum()),
        "cutoffs": len(set(groups.tolist())),
    }
    for metric_name in ("pr_auc", "roc_auc"):
        metric, difference = block_bootstrap(
            y, scores, groups, baseline="climatology", metric_name=metric_name
        )
        report[metric_name] = {name: _interval(item) for name, item in metric.items()}
        report[f"{metric_name}_minus_climatology"] = {
            name: _interval(item) for name, item in difference.items()
        }
    return report


def main() -> None:
    started = time.perf_counter()
    rows = load_dataset(DATASET_PATH)
    train = [row for row in rows if row.split == "train"]
    validation = [row for row in rows if row.split == "validation"]
    season_2025 = load_dataset(SEASON_2025_PATH)
    climatology = fit_climatology(train)
    history = (
        [row.tile_id for row in train],
        surface_index_components(train)["surface_hdw"],
    )

    config = {
        "index": INDEX_VERSION,
        "index_inputs": "2 m temperature, 2 m relative humidity, 10 m wind at cutoff",
        "cutoff_time_utc": "10:00",
        "target": "FIRMS fire in the cell in the 24 hours after the cutoff",
        "climatology_fit": "train split, 2019 to 2022",
        "local_percentile": "rank of the value among the same cell's 2019 to 2022 values",
        "periods": ["2023 (validation)", "2025 season"],
        "excluded": "2024 locked test year",
        "bootstrap": {
            "groups": "cutoff date",
            "samples": BOOTSTRAP_SAMPLES,
            "seed": BOOTSTRAP_SEED,
        },
    }
    results = [
        _evaluate("2023", validation, climatology, history),
        _evaluate("2025", season_2025, climatology, history),
    ]
    metrics = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(time.perf_counter() - started, 1),
        "results": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "config.json").write_text(json.dumps(config, indent=2), "utf-8")
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), "utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
