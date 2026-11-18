from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any


@dataclass(frozen=True)
class GpuSample:
    at: float
    utilization: float
    memory_gb: float
    sm_clock_mhz: float
    temperature_c: float
    power_w: float


Reader = Callable[[], GpuSample]


def nvml_reader(index: int) -> Reader | None:
    try:
        nvml: Any = importlib.import_module("pynvml")
        nvml.nvmlInit()
        handle = nvml.nvmlDeviceGetHandleByIndex(index)
    except Exception:
        return None

    def read() -> GpuSample:
        rates = nvml.nvmlDeviceGetUtilizationRates(handle)
        memory = nvml.nvmlDeviceGetMemoryInfo(handle)
        return GpuSample(
            at=time.time(),
            utilization=float(rates.gpu),
            memory_gb=memory.used / 1e9,
            sm_clock_mhz=float(nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_SM)),
            temperature_c=float(
                nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
            ),
            power_w=nvml.nvmlDeviceGetPowerUsage(handle) / 1000.0,
        )

    return read


class GpuMonitor:
    def __init__(self, reader: Reader | None, interval: float = 0.2):
        self.reader = reader
        self.interval = interval
        self.samples: list[GpuSample] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> GpuMonitor:
        if self.reader is not None:
            self._thread = threading.Thread(target=self._sample, daemon=True)
            self._thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _sample(self) -> None:
        assert self.reader is not None
        while not self._stop.is_set():
            self.samples.append(self.reader())
            self._stop.wait(self.interval)

    def summary(
        self, start: float | None = None, end: float | None = None
    ) -> dict[str, Any]:
        chosen = [
            sample
            for sample in self.samples
            if (start is None or sample.at >= start)
            and (end is None or sample.at <= end)
        ]
        if not chosen:
            return {"samples": 0}

        def mean(name: str) -> float:
            return round(sum(getattr(s, name) for s in chosen) / len(chosen), 2)

        return {
            "samples": len(chosen),
            "mean_utilization_percent": mean("utilization"),
            "mean_sm_clock_mhz": mean("sm_clock_mhz"),
            "min_sm_clock_mhz": min(s.sm_clock_mhz for s in chosen),
            "max_temperature_c": max(s.temperature_c for s in chosen),
            "mean_power_w": mean("power_w"),
            "max_memory_gb": round(max(s.memory_gb for s in chosen), 2),
        }
