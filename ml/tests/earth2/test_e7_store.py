from datetime import datetime, timezone

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    FEATURES,
    CutoffForecast,
    load_forecast_set,
    save_cutoff_forecast,
)


def _forecast(day: int, latitude=None) -> CutoffForecast:
    cutoff = datetime(2023, 8, day, 10, tzinfo=timezone.utc)
    return CutoffForecast(
        cutoff=cutoff,
        initialization=cutoff.replace(hour=6),
        latitude=np.array([38.0, 37.75]) if latitude is None else latitude,
        longitude=np.array([240.0, 240.25, 240.5]),
        features={name: np.full((3, 2, 3), float(day)) for name in FEATURES},
        approximate=True,
    )


def test_forecasts_round_trip_and_stack_in_cutoff_order(tmp_path) -> None:
    for day in (13, 6):
        save_cutoff_forecast(_forecast(day), tmp_path)

    stored = load_forecast_set(tmp_path)

    assert [cutoff.day for cutoff in stored.cutoffs] == [6, 13]
    assert stored.features["hdw_max"].shape == (2, 3, 2, 3)
    assert stored.features["hdw_max"][1, 0, 0, 0] == 13.0
    assert stored.index_of(stored.cutoffs[1]) == 1


def test_forecasts_on_different_grids_are_rejected(tmp_path) -> None:
    save_cutoff_forecast(_forecast(6), tmp_path)
    save_cutoff_forecast(_forecast(13, latitude=np.array([39.0, 38.75])), tmp_path)
    with pytest.raises(ValueError, match="different grid"):
        load_forecast_set(tmp_path)


def test_a_forecast_that_starts_after_its_cutoff_is_rejected(tmp_path) -> None:
    forecast = _forecast(6)
    late = CutoffForecast(
        **{**forecast.__dict__, "initialization": forecast.cutoff.replace(hour=12)}
    )
    save_cutoff_forecast(late, tmp_path)
    with pytest.raises(ValueError, match="after its cutoff"):
        load_forecast_set(tmp_path)
