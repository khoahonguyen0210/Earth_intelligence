from __future__ import annotations

import importlib
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (
    build_columns,
    crop_indices,
    daily_features,
    required_variables,
    select_fields,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    FEATURES,
    CutoffForecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    daily_valid_times,
    forecast_steps,
    initialization_time,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
)

IndexFunction = Callable[[ColumnFields], torch.Tensor]
KERNEL_PACKAGE = "ai_earth_intelligence_and_forecasting_engine.kernels"
INDEX_IMPLEMENTATIONS = {
    "eager": ("hdwi_reference", "compute_index"),
    "torch_compile": ("hdwi_compiled", "compiled_compute"),
    "triton": ("hdwi_triton", "triton_hot_dry_windy_index"),
    "cuda": ("hdwi_cuda", "cuda_hot_dry_windy_index"),
}
STAGES = (
    "model_load",
    "imports",
    "model_weights",
    "data_source",
    "data_loading",
    "host_to_device",
    "model_forward",
    "index",
    "index_kernel",
    "writing_output",
)


class StageTimer:
    def __init__(self, synchronize: bool = True):
        self.synchronize = synchronize and torch.cuda.is_available()
        self.seconds: dict[str, float] = defaultdict(float)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        if self.synchronize:
            torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.profiler.record_function(name):
            yield
        if self.synchronize:
            torch.cuda.synchronize()
        self.seconds[name] += time.perf_counter() - started

    def table(self, total_seconds: float) -> list[dict[str, Any]]:
        return [
            {
                "stage": name,
                "seconds": round(self.seconds.get(name, 0.0), 3),
                "share_of_total": round(self.seconds.get(name, 0.0) / total_seconds, 4),
            }
            for name in STAGES
        ]


def crop_columns(
    columns: ColumnFields, rows: np.ndarray, cols: np.ndarray
) -> ColumnFields:
    device = columns.t2m.device
    row_index = torch.as_tensor(rows, device=device)
    col_index = torch.as_tensor(cols, device=device)

    def crop(tensor: torch.Tensor) -> torch.Tensor:
        return tensor.index_select(-2, row_index).index_select(-1, col_index)

    return ColumnFields(
        **{
            name: value if name == "pressure" else crop(value)
            for name, value in columns.__dict__.items()
        }
    )


def index_step(
    output: torch.Tensor,
    output_coords: dict[str, np.ndarray],
    index_function: IndexFunction,
    timer: StageTimer,
) -> tuple[ColumnFields, np.ndarray, np.ndarray, bool]:
    everywhere = (
        np.arange(len(output_coords["lat"])),
        np.arange(len(output_coords["lon"])),
    )
    names = required_variables() + ["d2m"]
    fields = select_fields(output, output_coords, names, *everywhere)
    columns, approximate = build_columns(fields)
    with timer.stage("index_kernel"):
        index_function(columns)
    rows, cols = crop_indices(output_coords["lat"], output_coords["lon"])
    cropped = crop_columns(columns, rows, cols)
    return (
        cropped,
        output_coords["lat"][rows],
        output_coords["lon"][cols],
        approximate,
    )


def fetch_initial_state(
    data: Any, cutoff: datetime, variables: np.ndarray, lead_time: np.ndarray
) -> tuple[torch.Tensor, Any]:
    from earth2studio.data import fetch_data
    from earth2studio.utils.time import to_time_array

    start = initialization_time(cutoff).replace(tzinfo=None)
    return fetch_data(
        data,
        to_time_array([start]),
        variables,
        lead_time,
        device=torch.device("cpu"),
    )


def run_daily(
    model: Any,
    data: Any,
    cutoff: datetime,
    index_function: IndexFunction,
    timer: StageTimer,
    device: str = "cuda",
    prefetched: Future[tuple[torch.Tensor, Any]] | None = None,
    half_precision: bool = False,
) -> CutoffForecast:
    initialization = initialization_time(cutoff)
    lead_by_time = {
        valid: lead for lead in LEAD_DAYS for valid in daily_valid_times(cutoff, lead)
    }
    steps = forecast_steps(cutoff)
    coords = model.input_coords()
    with timer.stage("data_loading"):
        ready = prefetched.result() if prefetched else None
        if ready and list(ready[1]["variable"]) == list(coords["variable"]):
            x, x_coords = ready
        else:
            x, x_coords = fetch_initial_state(
                data, cutoff, coords["variable"], coords["lead_time"]
            )
        del ready
    with timer.stage("host_to_device"):
        x = x.to(device)

    snapshots: dict[int, list[ColumnFields]] = {lead: [] for lead in LEAD_DAYS}
    approximate = False
    latitude = longitude = np.empty(0)
    iterator = model.create_iterator(x, x_coords)
    del x
    precision = (
        torch.autocast("cuda", dtype=torch.float16) if half_precision else nullcontext()
    )
    with torch.inference_mode():
        for step in range(steps + 1):
            with timer.stage("model_forward"), precision:
                output, output_coords = next(iterator)
            hours = int(output_coords["lead_time"][-1] / np.timedelta64(1, "h"))
            valid = initialization + timedelta(hours=hours)
            if valid in lead_by_time:
                with timer.stage("index"):
                    cropped, latitude, longitude, approximate = index_step(
                        output, output_coords, index_function, timer
                    )
                snapshots[lead_by_time[valid]].append(cropped)
            del output

    with timer.stage("index"):
        by_lead = [daily_features(snapshots[lead]) for lead in LEAD_DAYS]
        features = {
            name: np.stack([day[name].double().cpu().numpy() for day in by_lead])
            for name in FEATURES
        }
    return CutoffForecast(
        cutoff=cutoff,
        initialization=initialization,
        latitude=np.asarray(latitude, dtype=np.float64),
        longitude=np.asarray(longitude, dtype=np.float64),
        features=features,
        approximate=approximate,
    )


def index_function(name: str) -> IndexFunction:
    module_name, attribute = INDEX_IMPLEMENTATIONS[name]
    module = importlib.import_module(f"{KERNEL_PACKAGE}.{module_name}")
    function = getattr(module, attribute)
    return function() if name == "torch_compile" else function
