from __future__ import annotations

import sys
import types
from collections import OrderedDict
from concurrent.futures import Future
from datetime import datetime, timezone

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.earth2.daily import (  # noqa: E402
    StageTimer,
    fetch_initial_state,
    index_function,
    run_daily,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (  # noqa: E402
    forecast_cutoff,
    required_variables,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (  # noqa: E402
    forecast_steps,
)

CUTOFF = datetime(2025, 8, 3, 10, tzinfo=timezone.utc)
LATITUDE = np.array([45.0, 40.0, 35.0, 30.0])
LONGITUDE = np.array([230.0, 236.0, 240.0, 246.0, 250.0])
VARIABLES = required_variables()


def initial_state() -> torch.Tensor:
    generator = torch.Generator().manual_seed(3)
    shape = (len(LATITUDE), len(LONGITUDE))
    fields = []
    for name in VARIABLES:
        noise = torch.rand(shape, generator=generator, dtype=torch.float64)
        if name == "sp":
            fields.append(95000.0 + 7000.0 * noise)
        elif name == "t2m" or name.startswith("t"):
            fields.append(280.0 + 25.0 * noise)
        elif name.startswith("q"):
            fields.append(0.002 + 0.01 * noise)
        else:
            fields.append(-12.0 + 24.0 * noise)
    return torch.stack(fields)[None, None, None]


class FakeModel:
    def input_coords(self) -> OrderedDict:
        return OrderedDict(
            batch=np.empty(0),
            time=np.empty(0),
            lead_time=np.array([np.timedelta64(0, "h")]),
            variable=np.array(VARIABLES),
            lat=LATITUDE,
            lon=LONGITUDE,
        )

    def create_iterator(self, x, coords):
        lead = np.timedelta64(0, "h")
        while True:
            step = coords.copy()
            step["lead_time"] = np.array([lead])
            yield x, step
            x = x * 1.01 + 0.1
            lead = lead + np.timedelta64(6, "h")


@pytest.fixture
def fake_earth2studio(monkeypatch):
    def fetch_data(data, time, variable, lead_time, device="cpu"):
        coords = OrderedDict(
            time=time,
            lead_time=lead_time,
            variable=np.array(variable),
            lat=LATITUDE,
            lon=LONGITUDE,
        )
        return initial_state()[0].to(device), coords

    package = types.ModuleType("earth2studio")
    data_module = types.ModuleType("earth2studio.data")
    data_module.fetch_data = fetch_data
    utils_module = types.ModuleType("earth2studio.utils")
    time_module = types.ModuleType("earth2studio.utils.time")
    time_module.to_time_array = lambda times: np.array(times)
    for name, module in {
        "earth2studio": package,
        "earth2studio.data": data_module,
        "earth2studio.utils": utils_module,
        "earth2studio.utils.time": time_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_daily_run_matches_the_e7_forecast_path(fake_earth2studio):
    timer = StageTimer(synchronize=False)
    daily = run_daily(
        FakeModel(), None, CUTOFF, index_function("eager"), timer, device="cpu"
    )
    reference = forecast_cutoff(FakeModel(), None, CUTOFF, device="cpu")

    assert forecast_steps(CUTOFF) == 11
    assert daily.approximate and reference.approximate
    np.testing.assert_array_equal(daily.latitude, reference.latitude)
    np.testing.assert_array_equal(daily.longitude, reference.longitude)
    for name, values in reference.features.items():
        np.testing.assert_allclose(daily.features[name], values, rtol=1e-12)
    assert timer.seconds["model_forward"] > 0
    assert timer.seconds["index_kernel"] > 0


def prefetched_state(variables) -> Future:
    lead_time = np.array([np.timedelta64(0, "h")])
    future: Future = Future()
    future.set_result(fetch_initial_state(None, CUTOFF, np.array(variables), lead_time))
    return future


def test_prefetched_initial_state_gives_the_same_forecast(fake_earth2studio):
    eager = index_function("eager")
    plain = run_daily(FakeModel(), None, CUTOFF, eager, StageTimer(), device="cpu")
    for variables in (VARIABLES, VARIABLES[:-1]):
        early = run_daily(
            FakeModel(),
            None,
            CUTOFF,
            eager,
            StageTimer(),
            device="cpu",
            prefetched=prefetched_state(variables),
        )
        for name, values in plain.features.items():
            np.testing.assert_array_equal(early.features[name], values)
