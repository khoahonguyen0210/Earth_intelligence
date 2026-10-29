from __future__ import annotations

import csv
import json
import platform
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.kernels.fixtures import (
    FCN3_LEVELS,
    edge_case_columns,
    random_columns,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
    compute_index,
    hot_dry_windy_index,
    layer_mask,
)

ABSOLUTE_TOLERANCE = 1e-3
RELATIVE_TOLERANCE = 1e-4
WARMUP_RUNS = 10
TIMED_RUNS = 50
GLOBAL_GRID = (721, 1440)
DATASHEET_BANDWIDTH_GBPS = 320.0

Prepared = Callable[[], torch.Tensor]
Preparer = Callable[[ColumnFields], Prepared]


@dataclass(frozen=True)
class Size:
    name: str
    batch: int


@dataclass(frozen=True)
class Measurement:
    implementation: str
    size: str
    batch: int
    columns: int
    levels: int
    status: str
    median_ms: float
    p90_ms: float
    bytes_moved: int
    effective_gbps: float
    percent_of_peak: float
    max_absolute_error: float
    max_relative_error: float
    within_tolerance: bool


def preparers() -> dict[str, Preparer]:
    from ai_earth_intelligence_and_forecasting_engine.kernels import (
        hdwi_cuda,
        hdwi_triton,
    )
    from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_compiled import (
        compiled_compute,
    )
    from ai_earth_intelligence_and_forecasting_engine.kernels.layout import pack

    def eager(columns: ColumnFields) -> Prepared:
        return lambda: compute_index(columns)

    def compiled(columns: ColumnFields) -> Prepared:
        function = compiled_compute()
        return lambda: function(columns)

    def triton(columns: ColumnFields) -> Prepared:
        packed = pack(columns)
        return lambda: hdwi_triton.launch(packed)

    def cuda(columns: ColumnFields) -> Prepared:
        packed = pack(columns)
        return lambda: hdwi_cuda.launch(packed)

    return {"eager": eager, "torch_compile": compiled, "triton": triton, "cuda": cuda}


def environment() -> dict[str, str]:
    def run(command: list[str]) -> str:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unavailable"

    try:
        import triton

        triton_version = str(triton.__version__)
    except ImportError:
        triton_version = "unavailable"

    nvcc = run(["nvcc", "--version"])
    return {
        "gpu": torch.cuda.get_device_name(0),
        "driver": run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
        ),
        "torch": torch.__version__,
        "torch_cuda": str(torch.version.cuda),
        "triton": triton_version,
        "nvcc": nvcc.splitlines()[-1] if nvcc != "unavailable" else nvcc,
        "python": platform.python_version(),
    }


def time_ms(function: Callable[[], object], warmup: int, runs: int) -> np.ndarray:
    for _ in range(warmup):
        function()
    torch.cuda.synchronize()
    times = []
    for _ in range(runs):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        function()
        end.record()
        end.synchronize()
        times.append(start.elapsed_time(end))
    return np.array(times)


def peak_bandwidth_gbps(megabytes: int = 1024, runs: int = TIMED_RUNS) -> float:
    count = megabytes * 1024 * 1024 // 4
    source = torch.empty(count, device="cuda", dtype=torch.float32)
    target = torch.empty_like(source)
    times = time_ms(lambda: target.copy_(source), WARMUP_RUNS, runs)
    moved = 2 * source.numel() * source.element_size()
    return moved / (float(np.median(times)) * 1e-3) / 1e9


def member(columns: ColumnFields, index: int) -> ColumnFields:
    return ColumnFields(
        **{
            item.name: getattr(columns, item.name)[index : index + 1]
            if item.name != "pressure"
            else columns.pressure
            for item in fields(columns)
        }
    )


def exact_index(columns: ColumnFields) -> torch.Tensor:
    device = columns.t2m.device
    if columns.t2m.ndim == 2:
        return hot_dry_windy_index(columns.to(device, torch.float64))
    return torch.cat(
        [
            hot_dry_windy_index(member(columns, index).to(device, torch.float64))
            for index in range(columns.t2m.shape[0])
        ]
    )


def bytes_moved(columns: ColumnFields) -> int:
    used = 0
    for index in range(columns.t2m.shape[0]):
        part = member(columns, index)
        used += int(layer_mask(part.pressure, part.surface_pressure / 100.0).sum())
    cells = columns.t2m.numel()
    return 4 * (6 * cells + 4 * used)


def errors(result: torch.Tensor, exact: torch.Tensor) -> tuple[float, float, bool]:
    result = result.double()
    if not torch.equal(torch.isnan(result), torch.isnan(exact)):
        return float("nan"), float("nan"), False
    finite = torch.isfinite(exact)
    difference = (result[finite] - exact[finite]).abs()
    if difference.numel() == 0:
        return 0.0, 0.0, True
    size = exact[finite].abs()
    allowed = ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * size
    relative = difference / size.clamp(min=ABSOLUTE_TOLERANCE)
    return (
        float(difference.max()),
        float(relative.max()),
        bool(torch.all(difference <= allowed)),
    )


def within_tolerance(result: torch.Tensor, exact: torch.Tensor) -> bool:
    return errors(result, exact)[2]


def check_edge_cases(prepare: Preparer) -> bool:
    columns = edge_case_columns(dtype=torch.float32, device="cuda")
    return within_tolerance(prepare(columns)(), exact_index(columns))


def measure(
    name: str,
    prepare: Preparer,
    columns: ColumnFields,
    exact: torch.Tensor,
    moved: int,
    size: Size,
    peak: float,
) -> Measurement:
    failed = Measurement(
        implementation=name,
        size=size.name,
        batch=size.batch,
        columns=int(columns.t2m.shape[-2] * columns.t2m.shape[-1]),
        levels=int(columns.pressure.numel()),
        status="out_of_memory",
        median_ms=float("nan"),
        p90_ms=float("nan"),
        bytes_moved=moved,
        effective_gbps=float("nan"),
        percent_of_peak=float("nan"),
        max_absolute_error=float("nan"),
        max_relative_error=float("nan"),
        within_tolerance=False,
    )
    try:
        function = prepare(columns)
        times = time_ms(function, WARMUP_RUNS, TIMED_RUNS)
        absolute, relative, passed = errors(function(), exact)
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        return failed
    median = float(np.median(times))
    gbps = moved / (median * 1e-3) / 1e9
    return replace(
        failed,
        status="ok",
        median_ms=round(median, 4),
        p90_ms=round(float(np.percentile(times, 90)), 4),
        effective_gbps=round(gbps, 2),
        percent_of_peak=round(100 * gbps / peak, 1),
        max_absolute_error=absolute,
        max_relative_error=relative,
        within_tolerance=passed,
    )


def plot(measurements: list[Measurement], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sizes = list(dict.fromkeys(item.size for item in measurements))
    names = list(dict.fromkeys(item.implementation for item in measurements))
    width = 0.8 / len(names)
    figure, axis = plt.subplots(figsize=(8, 4))
    for offset, name in enumerate(names):
        values = []
        for size in sizes:
            match = [
                item.percent_of_peak
                for item in measurements
                if item.implementation == name
                and item.size == size
                and item.status == "ok"
            ]
            values.append(match[0] if match else 0.0)
        positions = [index + offset * width for index in range(len(sizes))]
        axis.bar(positions, values, width, label=name)
    axis.set_xticks([index + 0.4 - width / 2 for index in range(len(sizes))], sizes)
    axis.set_ylabel("Share of measured peak bandwidth (%)")
    axis.set_ylim(0, 100)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def run(sizes: list[Size], output_dir: Path) -> list[Measurement]:
    output_dir.mkdir(parents=True, exist_ok=True)
    peak = peak_bandwidth_gbps()
    torch.cuda.empty_cache()
    candidates = preparers()
    edge_cases = {
        name: check_edge_cases(prepare) for name, prepare in candidates.items()
    }

    measurements = []
    height, width = GLOBAL_GRID
    for size in sizes:
        columns = random_columns(
            (size.batch,), height, width, FCN3_LEVELS, seed=11, device="cuda"
        )
        exact = exact_index(columns)
        moved = bytes_moved(columns)
        for name, prepare in candidates.items():
            if edge_cases[name]:
                measurements.append(
                    measure(name, prepare, columns, exact, moved, size, peak)
                )
            torch.cuda.empty_cache()
        del columns, exact
        torch.cuda.empty_cache()

    with (output_dir / "kernel_benchmark.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=[item.name for item in fields(Measurement)]
        )
        writer.writeheader()
        writer.writerows(asdict(item) for item in measurements)
    summary = {
        "environment": environment(),
        "peak_bandwidth_gbps": round(peak, 2),
        "datasheet_bandwidth_gbps": DATASHEET_BANDWIDTH_GBPS,
        "edge_cases_passed": edge_cases,
        "tolerance": {"absolute": ABSOLUTE_TOLERANCE, "relative": RELATIVE_TOLERANCE},
        "warmup_runs": WARMUP_RUNS,
        "timed_runs": TIMED_RUNS,
        "sizes": [asdict(size) for size in sizes],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    plot(measurements, output_dir / "percent_of_peak.png")
    return measurements
