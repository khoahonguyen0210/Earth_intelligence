import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.earth2.daily import (
    fetch_initial_state,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.ensemble import (
    NOISE_SCALE,
    NOISE_SEED,
    load_ensemble,
    merge_ensembles,
    run_members,
    save_ensemble,
    split_members,
    spread_by_lead,
    warm_throughput,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.gpu_monitor import (
    GpuMonitor,
    nvml_reader,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.imports import (
    lean_earth2studio,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.memory import (
    reduce_peak_memory,
)

DEFAULT_CUTOFF = "2025-08-03T10:00:00+00:00"


def prepare_initial_state(path: Path, cutoff: datetime, model_name: str) -> float:
    if path.exists():
        return 0.0
    started = time.perf_counter()
    model_class = lean_earth2studio(model_name)
    from earth2studio.data import ARCO

    variables = np.array(importlib.import_module(model_class.__module__).VARIABLES)
    lead_time = np.array([np.timedelta64(0, "h")])
    x, coords = fetch_initial_state(ARCO(), cutoff, variables, lead_time)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"x": x, "coords": dict(coords)}, path)
    return time.perf_counter() - started


def worker(arguments) -> int:
    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    stages = {}
    started = time.perf_counter()
    model_class = lean_earth2studio(arguments.model)
    stages["imports"] = time.perf_counter() - started

    mark = time.perf_counter()
    model = model_class.load_model(model_class.load_default_package())
    chunked = reduce_peak_memory(model)
    model = model.to("cuda").eval()
    torch.cuda.synchronize()
    stages["model_weights"] = time.perf_counter() - mark
    model_memory_gb = torch.cuda.memory_allocated() / 1e9

    mark = time.perf_counter()
    saved = torch.load(arguments.initial_state, weights_only=False)
    x, coords = saved["x"], OrderedDict(saved["coords"])
    expected = [str(name) for name in model.input_coords()["variable"]]
    if [str(name) for name in coords["variable"]] != expected:
        raise SystemExit("the saved initial state has different variables")
    stages["initial_state"] = time.perf_counter() - mark

    members = [int(value) for value in arguments.member_list.split(",")]
    cutoff = datetime.fromisoformat(arguments.cutoff)
    summary = {
        "gpu_index": arguments.gpu_index,
        "gpu": torch.cuda.get_device_name(0),
        "members": members,
        "batch_size": arguments.batch_size,
        "chunked_layers": chunked,
        "model_memory_gb": round(model_memory_gb, 2),
    }
    monitor = GpuMonitor(nvml_reader(arguments.gpu_index))
    try:
        with monitor:
            forecast, records = run_members(
                model, x, coords, cutoff, members, arguments.batch_size
            )
    except torch.cuda.OutOfMemoryError as error:
        summary.update(
            completed=False,
            error="out_of_memory",
            message=str(error).splitlines()[0],
            peak_memory_gb=round(torch.cuda.max_memory_allocated() / 1e9, 2),
            stages={name: round(value, 2) for name, value in stages.items()},
        )
        (output / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
        return 3

    save_ensemble(forecast, output / "members.npz")
    first, last = records[0], records[-1]
    stages["forecast"] = last.finished_at - first.started_at
    summary.update(
        completed=True,
        stages={name: round(value, 2) for name, value in stages.items()},
        forecast_started_at=first.started_at,
        forecast_finished_at=last.finished_at,
        warm_member_steps_per_second=round(warm_throughput(records), 4),
        peak_memory_gb=round(max(record.peak_memory_gb for record in records), 2),
        batches=[
            {
                "members": record.members,
                "seconds": round(record.seconds, 2),
                "peak_memory_gb": round(record.peak_memory_gb, 2),
            }
            for record in records
        ],
        gpu_activity=monitor.summary(first.started_at, last.finished_at),
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    return 0


def last_lines(path: Path, count: int = 8) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]


def parent(arguments) -> int:
    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.fromisoformat(arguments.cutoff)
    fetch_seconds = prepare_initial_state(
        arguments.initial_state, cutoff, arguments.model
    )
    groups = split_members(arguments.members, arguments.gpus)

    started = time.time()
    processes = []
    for index, group in enumerate(groups):
        environment = {
            **os.environ,
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "CUDA_VISIBLE_DEVICES": str(index),
            "PYTORCH_CUDA_ALLOC_CONF": os.environ.get(
                "PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True"
            ),
        }
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--gpu-index",
            str(index),
            "--member-list",
            ",".join(str(member) for member in group),
            "--batch-size",
            str(arguments.batch_size),
            "--cutoff",
            arguments.cutoff,
            "--model",
            arguments.model,
            "--initial-state",
            str(arguments.initial_state),
            "--output",
            str(output / f"worker_{index}"),
        ]
        log = (output / f"worker_{index}.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            command, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        processes.append((process, log))
    codes = []
    for process, log in processes:
        codes.append(process.wait())
        log.close()
    finished = time.time()

    workers = []
    for index in range(len(groups)):
        path = output / f"worker_{index}" / "summary.json"
        workers.append(
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {"completed": False, "log": last_lines(output / f"worker_{index}.log")}
        )
    completed = all(code == 0 for code in codes)
    summary = {
        "cutoff": arguments.cutoff,
        "members": arguments.members,
        "batch_size": arguments.batch_size,
        "gpus": arguments.gpus,
        "noise_scale": NOISE_SCALE,
        "noise_seed": NOISE_SEED,
        "torch": torch.__version__,
        "cpu_count": os.cpu_count(),
        "initial_state_fetch_seconds": round(fetch_seconds, 2),
        "return_codes": codes,
        "completed": completed,
        "wall_seconds": round(finished - started, 2),
        "peak_memory_gb": max(
            (item.get("peak_memory_gb", 0.0) for item in workers), default=0.0
        ),
        "workers": workers,
    }
    if completed:
        forecast_seconds = max(w["forecast_finished_at"] for w in workers) - min(
            w["forecast_started_at"] for w in workers
        )
        ensemble = merge_ensembles(
            [
                load_ensemble(output / f"worker_{i}" / "members.npz")
                for i in range(len(groups))
            ]
        )
        save_ensemble(ensemble, output / "ensemble.npz")
        summary.update(
            forecast_wall_seconds=round(forecast_seconds, 2),
            members_per_minute=round(arguments.members / forecast_seconds * 60, 3),
            warm_member_steps_per_second=round(
                sum(w["warm_member_steps_per_second"] for w in workers), 4
            ),
            hdw_spread_by_lead=spread_by_lead(ensemble),
        )
    (output / "summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "workers"}, indent=2))
    return 0 if completed else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    parser.add_argument("--model", default="SFNO")
    parser.add_argument("--members", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gpus", type=int, default=1)
    parser.add_argument("--initial-state", type=Path, default=Path("initial_state.pt"))
    parser.add_argument("--output", type=Path, default=Path("ensemble"))
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--member-list", default="")
    arguments = parser.parse_args()
    sys.exit(worker(arguments) if arguments.worker else parent(arguments))


if __name__ == "__main__":
    main()
