import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import torch

from ai_earth_intelligence_and_forecasting_engine.earth2.daily import (
    INDEX_IMPLEMENTATIONS,
    StageTimer,
    index_function,
    run_daily,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (
    APPROXIMATE_INDEX_VERSION,
    INDEX_VERSION,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    save_cutoff_forecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import daily_cutoff


def load(model_name: str, source: str):
    from earth2studio.data import ARCO, GFS
    from earth2studio.models import px

    model_class = getattr(px, model_name)
    model = model_class.load_model(model_class.load_default_package())
    return model.to("cuda").eval(), GFS() if source == "gfs" else ARCO()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff")
    parser.add_argument("--output", type=Path, default=Path("daily"))
    parser.add_argument("--model", default="SFNO")
    parser.add_argument("--source", choices=("gfs", "arco"), default="gfs")
    parser.add_argument(
        "--implementation", choices=sorted(INDEX_IMPLEMENTATIONS), default="eager"
    )
    parser.add_argument("--profile", action="store_true")
    arguments = parser.parse_args()

    cutoff = (
        datetime.fromisoformat(arguments.cutoff)
        if arguments.cutoff
        else daily_cutoff(datetime.now(timezone.utc))
    )
    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    timer = StageTimer()
    torch.cuda.reset_peak_memory_stats()
    with timer.stage("model_load"):
        model, data = load(arguments.model, arguments.source)
        index = index_function(arguments.implementation)
    forecast = run_daily(model, data, cutoff, index, timer)
    with timer.stage("writing_output"):
        save_cutoff_forecast(forecast, output)
    total = time.perf_counter() - started

    import earth2studio

    summary = {
        "cutoff": cutoff.isoformat(),
        "forecast_start": forecast.initialization.isoformat(),
        "weather_model": arguments.model,
        "data_source": arguments.source,
        "index_version": (
            APPROXIMATE_INDEX_VERSION if forecast.approximate else INDEX_VERSION
        ),
        "index_implementation": arguments.implementation,
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "earth2studio": earth2studio.__version__,
        "total_seconds": round(total, 2),
        "peak_memory_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
        "stages": timer.table(total),
    }

    if arguments.profile:
        from torch.profiler import ProfilerActivity, profile

        activities = [ProfilerActivity.CPU, ProfilerActivity.CUDA]
        with profile(activities=activities) as profiler:
            run_daily(model, data, cutoff, index, StageTimer())
        averages = profiler.key_averages()
        (output / "profile_table.txt").write_text(
            averages.table(sort_by="cuda_time_total", row_limit=40), "utf-8"
        )

    (output / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
