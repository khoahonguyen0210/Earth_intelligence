from __future__ import annotations

import itertools

from ai_earth_intelligence_and_forecasting_engine.earth2 import gpu_monitor
from ai_earth_intelligence_and_forecasting_engine.earth2.gpu_monitor import (
    GpuMonitor,
    GpuSample,
    nvml_reader,
)


def counting_reader():
    counter = itertools.count()

    def read() -> GpuSample:
        number = next(counter)
        return GpuSample(
            at=float(number),
            utilization=90.0 + number % 2 * 10,
            memory_gb=10.0 + number,
            sm_clock_mhz=1500.0 - number,
            temperature_c=60.0 + number,
            power_w=70.0,
        )

    return read


def test_monitor_samples_until_it_stops():
    with GpuMonitor(counting_reader(), interval=0.001) as monitor:
        while len(monitor.samples) < 5:
            pass
    count = len(monitor.samples)
    assert count >= 5
    assert len(monitor.samples) == count


def test_summary_covers_only_the_chosen_window():
    monitor = GpuMonitor(None)
    read = counting_reader()
    monitor.samples = [read() for _ in range(6)]
    summary = monitor.summary(start=2.0, end=5.0)
    assert summary["samples"] == 4
    assert summary["mean_utilization_percent"] == 95.0
    assert summary["min_sm_clock_mhz"] == 1495.0
    assert summary["max_temperature_c"] == 65.0
    assert summary["max_memory_gb"] == 15.0
    assert monitor.summary(start=10.0) == {"samples": 0}


def test_monitor_without_a_reader_records_nothing():
    with GpuMonitor(None) as monitor:
        pass
    assert monitor.summary() == {"samples": 0}


def test_missing_nvml_gives_no_reader(monkeypatch):
    def fail(name):
        raise ImportError(name)

    monkeypatch.setattr(gpu_monitor.importlib, "import_module", fail)
    assert nvml_reader(0) is None
