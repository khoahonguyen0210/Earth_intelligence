import argparse
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    LOOKBACK_HOURS,
    load_firms_history,
)
from ai_earth_intelligence_and_forecasting_engine.data.live import (
    LIVE_FIRMS_PRODUCT,
    ensure_live_firms,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.daily_map import (
    load_cell_geography,
    map_rows,
    risk_payload,
    update_runs,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    load_cutoff_forecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import LEAD_DAYS
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    fire_history_features as fhf,
)

MAP_DIR = Path("map")


def previous_runs(url: str | None) -> list[dict]:
    if not url:
        return []
    try:
        response = requests.get(f"{url.rstrip('/')}/runs.json", timeout=30)
        response.raise_for_status()
        runs = response.json()
    except (requests.RequestException, ValueError):
        return []
    return runs if isinstance(runs, list) else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("site_build"))
    parser.add_argument("--site-url")
    parser.add_argument("--run-started")
    parser.add_argument("--expected-cutoff")
    arguments = parser.parse_args()

    forecast_files = sorted(arguments.forecast.rglob("forecast_*.npz"))
    if len(forecast_files) != 1:
        raise SystemExit(f"expected one forecast file in {arguments.forecast}")
    forecast = load_cutoff_forecast(forecast_files[0])
    summary_path = forecast_files[0].parent / "summary.json"
    summary = json.loads(summary_path.read_text("utf-8"))
    cutoff = forecast.cutoff
    if arguments.expected_cutoff and cutoff != datetime.fromisoformat(
        arguments.expected_cutoff
    ):
        raise SystemExit(f"the GPU run returned {cutoff}, not today's cutoff")

    model_metadata = json.loads((MAP_DIR / "models" / "metadata.json").read_text())
    models = {
        lead: json.loads((MAP_DIR / "models" / f"lead_{lead}.json").read_text())
        for lead in LEAD_DAYS
    }
    cells = build_california_grid()
    geography = load_cell_geography(MAP_DIR / "cells.csv")

    with tempfile.TemporaryDirectory() as live:
        live_dir = Path(live)
        ensure_live_firms(live_dir, cutoff)
        observations = load_firms_history(
            live_dir,
            cutoff - timedelta(hours=LOOKBACK_HOURS),
            cutoff,
            LIVE_FIRMS_PRODUCT,
        )
    fire_history = {
        record.tile_id: record
        for record in fhf.compute_fire_history_features(observations, cells, [cutoff])
    }
    rows_by_lead = {
        lead: map_rows(cells, geography, fire_history, forecast, lead)
        for lead in LEAD_DAYS
    }
    payload = risk_payload(
        forecast,
        models,
        rows_by_lead,
        {
            **model_metadata,
            "weather_model": summary["weather_model"],
            "index_version": summary["index_version"],
        },
    )

    finished = datetime.now(timezone.utc)
    started = (
        datetime.fromisoformat(arguments.run_started)
        if arguments.run_started
        else None
    )
    run = {
        "cutoff": cutoff.isoformat(),
        "status": "succeeded",
        "started": started.isoformat() if started else None,
        "finished": finished.isoformat(),
        "minutes": (
            round((finished - started).total_seconds() / 60, 1) if started else None
        ),
        "gpu_seconds": summary["total_seconds"],
        "fire_detections": len(observations),
    }
    runs = update_runs(previous_runs(arguments.site_url), run)

    output = arguments.output
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(MAP_DIR / "site", output)
    (output / "risk.json").write_text(json.dumps(payload), "utf-8")
    (output / "runs.json").write_text(json.dumps(runs, indent=1), "utf-8")
    (output / "pipeline.json").write_text(json.dumps(summary, indent=1), "utf-8")
    print(json.dumps(run, indent=2))


if __name__ == "__main__":
    main()
