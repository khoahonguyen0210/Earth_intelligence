import argparse
import importlib
import json
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.earth2.daily import (
    INDEX_IMPLEMENTATIONS,
    StageTimer,
    fetch_initial_state,
    index_function,
    run_daily,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (
    APPROXIMATE_INDEX_VERSION,
    INDEX_VERSION,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.memory import (
    CHANNELS_PER_CHUNK,
    ROWS_PER_CHUNK,
    chunk_pixel_layers,
    chunk_spectral_transforms,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    save_cutoff_forecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import daily_cutoff


def open_source(source: str):
    from earth2studio.data import ARCO, GFS

    return GFS() if source == "gfs" else ARCO()


def prefetch(source: str, cutoff: datetime, model_class) -> tuple[torch.Tensor, object]:
    variables = np.array(importlib.import_module(model_class.__module__).VARIABLES)
    lead_time = np.array([np.timedelta64(0, "h")])
    return fetch_initial_state(open_source(source), cutoff, variables, lead_time)


def load(arguments, cutoff: datetime, timer: StageTimer, pool: ThreadPoolExecutor):
    with timer.stage("imports"):
        importlib.import_module("earth2studio.data")
        px = importlib.import_module("earth2studio.models.px")
        model_class = getattr(px, arguments.model)
    prefetched: Future | None = None
    if arguments.overlap_loading:
        prefetched = pool.submit(prefetch, arguments.source, cutoff, model_class)
    with timer.stage("model_weights"):
        model = model_class.load_model(model_class.load_default_package())
        if arguments.rows_per_chunk:
            chunk_pixel_layers(model, arguments.rows_per_chunk)
        if arguments.channels_per_chunk:
            chunk_spectral_transforms(model, arguments.channels_per_chunk)
        model = model.to("cuda").eval()
    with timer.stage("data_source"):
        data = open_source(arguments.source)
    return model, data, prefetched


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
    parser.add_argument(
        "--rows-per-chunk",
        type=int,
        default=ROWS_PER_CHUNK,
        help="0 runs the per-pixel layers on the whole grid at once",
    )
    parser.add_argument(
        "--channels-per-chunk",
        type=int,
        default=CHANNELS_PER_CHUNK,
        help="0 runs the spherical harmonic transforms on all channels at once",
    )
    parser.add_argument("--overlap-loading", action="store_true")
    parser.add_argument("--cudnn-benchmark", action="store_true")
    parser.add_argument("--half-precision", action="store_true")
    arguments = parser.parse_args()
    torch.backends.cudnn.benchmark = arguments.cudnn_benchmark

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
    pool = ThreadPoolExecutor(max_workers=1)
    with timer.stage("model_load"):
        model, data, prefetched = load(arguments, cutoff, timer, pool)
        index = index_function(arguments.implementation)
    forecast = run_daily(
        model,
        data,
        cutoff,
        index,
        timer,
        prefetched=prefetched,
        half_precision=arguments.half_precision,
    )
    pool.shutdown()
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
        "rows_per_chunk": arguments.rows_per_chunk,
        "channels_per_chunk": arguments.channels_per_chunk,
        "overlap_loading": arguments.overlap_loading,
        "cudnn_benchmark": arguments.cudnn_benchmark,
        "half_precision": arguments.half_precision,
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
            run_daily(
                model,
                data,
                cutoff,
                index,
                StageTimer(),
                half_precision=arguments.half_precision,
            )
        averages = profiler.key_averages()
        (output / "profile_table.txt").write_text(
            averages.table(sort_by="cuda_time_total", row_limit=40), "utf-8"
        )

    (output / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
