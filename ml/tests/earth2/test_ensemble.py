from __future__ import annotations

import sys
import types
from collections import OrderedDict
from datetime import datetime, timezone

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ai_earth_intelligence_and_forecasting_engine.earth2.ensemble import (  # noqa: E402
    BatchRecord,
    agreement,
    load_ensemble,
    member_columns,
    merge_ensembles,
    perturb,
    run_members,
    save_ensemble,
    split_members,
    spread_by_lead,
    warm_throughput,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (  # noqa: E402
    forecast_cutoff,
    required_variables,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (  # noqa: E402
    FEATURES,
)

CUTOFF = datetime(2025, 8, 3, 10, tzinfo=timezone.utc)
LATITUDE = np.array([45.0, 40.0, 35.0, 30.0])
LONGITUDE = np.array([230.0, 236.0, 240.0, 246.0, 250.0])
VARIABLES = required_variables()


def initial_state() -> torch.Tensor:
    generator = torch.Generator().manual_seed(5)
    shape = (len(LATITUDE), len(LONGITUDE))
    fields = []
    for name in VARIABLES:
        noise = torch.rand(shape, generator=generator, dtype=torch.float64)
        if name == "sp":
            fields.append(95000.0 + 7000.0 * noise)
        elif name.startswith("t"):
            fields.append(280.0 + 25.0 * noise)
        elif name.startswith("q"):
            fields.append(0.002 + 0.01 * noise)
        else:
            fields.append(-12.0 + 24.0 * noise)
    return torch.stack(fields)[None, None]


def state_coords() -> OrderedDict:
    return OrderedDict(
        time=np.array([np.datetime64("2025-08-03T06:00")]),
        lead_time=np.array([np.timedelta64(0, "h")]),
        variable=np.array(VARIABLES),
        lat=LATITUDE,
        lon=LONGITUDE,
    )


class FakeModel:
    def input_coords(self) -> OrderedDict:
        return OrderedDict(batch=np.empty(0)) | state_coords()

    def create_iterator(self, x, coords):
        lead = np.timedelta64(0, "h")
        while True:
            step = coords.copy()
            step["lead_time"] = np.array([lead])
            yield x, step
            x = x * 1.001
            lead = lead + np.timedelta64(6, "h")


@pytest.fixture
def fake_earth2studio(monkeypatch):
    def fetch_data(data, time, variable, lead_time, device="cpu"):
        return initial_state().to(device), state_coords()

    data_module = types.ModuleType("earth2studio.data")
    data_module.fetch_data = fetch_data
    time_module = types.ModuleType("earth2studio.utils.time")
    time_module.to_time_array = lambda times: np.array(times)
    for name, module in {
        "earth2studio": types.ModuleType("earth2studio"),
        "earth2studio.data": data_module,
        "earth2studio.utils": types.ModuleType("earth2studio.utils"),
        "earth2studio.utils.time": time_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def run(members, batch_size):
    return run_members(
        FakeModel(),
        initial_state(),
        state_coords(),
        CUTOFF,
        members,
        batch_size,
        device="cpu",
    )


def test_members_are_split_evenly_across_workers():
    assert split_members(8, 2) == [[0, 1, 2, 3], [4, 5, 6, 7]]
    assert split_members(5, 2) == [[0, 1, 2], [3, 4]]
    assert split_members(3, 1) == [[0, 1, 2]]
    with pytest.raises(ValueError):
        split_members(1, 2)
    with pytest.raises(ValueError):
        split_members(4, 0)


def test_member_noise_does_not_depend_on_the_batch():
    x = initial_state()
    together = perturb(x, [0, 1, 2])
    alone = perturb(x, [2])
    torch.testing.assert_close(together[0], x, rtol=0, atol=0)
    torch.testing.assert_close(together[2], alone[0], rtol=0, atol=0)
    assert not torch.equal(together[1], together[2])


def test_control_member_matches_the_single_forecast(fake_earth2studio):
    ensemble, _ = run([0, 1, 2], batch_size=2)
    single = forecast_cutoff(FakeModel(), None, CUTOFF, device="cpu")
    np.testing.assert_array_equal(ensemble.latitude, single.latitude)
    np.testing.assert_array_equal(ensemble.longitude, single.longitude)
    for name in FEATURES:
        assert ensemble.features[name].shape == (3, 3, 2, 3)
        np.testing.assert_allclose(
            ensemble.features[name][0], single.features[name], rtol=1e-12
        )


def test_batch_size_does_not_change_any_member():
    one_by_one, records = run([0, 1, 2, 3], batch_size=1)
    batched, batched_records = run([0, 1, 2, 3], batch_size=3)
    for name in FEATURES:
        np.testing.assert_array_equal(one_by_one.features[name], batched.features[name])
    assert [record.members for record in records] == [[0], [1], [2], [3]]
    assert [record.members for record in batched_records] == [[0, 1, 2], [3]]
    assert all(record.member_steps == len(record.members) * 11 for record in records)


def test_perturbed_members_spread_around_the_control():
    ensemble, _ = run([0, 1, 2], batch_size=3)
    control = ensemble.features["hdw_max"][0]
    assert not np.allclose(ensemble.features["hdw_max"][1], control)
    assert all(value > 0 for value in spread_by_lead(ensemble))


def test_ensembles_save_load_and_merge_in_member_order(tmp_path):
    first, _ = run([2, 3], batch_size=2)
    second, _ = run([0, 1], batch_size=2)
    merged = merge_ensembles([first, second])
    np.testing.assert_array_equal(merged.members, [0, 1, 2, 3])
    whole, _ = run([0, 1, 2, 3], batch_size=4)
    path = tmp_path / "ensemble.npz"
    save_ensemble(merged, path)
    loaded = load_ensemble(path)
    assert loaded.cutoff == CUTOFF
    assert loaded.approximate == merged.approximate
    for name in FEATURES:
        np.testing.assert_array_equal(loaded.features[name], whole.features[name])


def test_member_columns_need_the_member_dimension():
    output = initial_state()[None]
    with pytest.raises(ValueError):
        member_columns(output[0], state_coords(), np.array([1]), np.array([1]))


def test_agreement_uses_the_forecast_tolerance():
    reference = np.array([[1.0, np.nan], [100.0, 5.0]])
    assert agreement(reference.copy(), reference)["identical"]
    close = reference + np.array([[0.005, 0.0], [0.05, 0.0]])
    result = agreement(close, reference)
    assert not result["identical"] and result["within_tolerance"]
    far = reference + np.array([[0.5, 0.0], [0.0, 0.0]])
    assert not agreement(far, reference)["within_tolerance"]
    moved = reference.copy()
    moved[0, 1] = 1.0
    assert not agreement(moved, reference)["within_tolerance"]


def test_warm_throughput_leaves_out_the_first_batch():
    records = [
        BatchRecord([0], 11, 20.0, 1.0, 0.0, 20.0),
        BatchRecord([1, 2], 11, 11.0, 1.0, 20.0, 31.0),
        BatchRecord([3, 4], 11, 11.0, 1.0, 31.0, 42.0),
    ]
    assert warm_throughput(records) == pytest.approx(2.0)
    assert warm_throughput(records[:1]) == pytest.approx(11 / 20)
