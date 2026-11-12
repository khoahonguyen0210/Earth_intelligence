from datetime import datetime, timezone

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import build_california_grid
from ai_earth_intelligence_and_forecasting_engine.earth2.daily_map import (
    CellGeography,
    load_cell_geography,
    map_rows,
    risk_payload,
    save_cell_geography,
    update_runs,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    FEATURES,
    CutoffForecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import daily_cutoff
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    fire_history_features as fhf,
)

CUTOFF = datetime(2026, 11, 10, 10, tzinfo=timezone.utc)


def _forecast() -> CutoffForecast:
    latitude = np.arange(43.0, 31.25, -0.25)
    longitude = np.arange(234.5, 247.25, 0.25)
    return CutoffForecast(
        cutoff=CUTOFF,
        initialization=CUTOFF.replace(hour=6),
        latitude=latitude,
        longitude=longitude,
        features={
            name: np.full((3, latitude.size, longitude.size), 10.0 * (index + 1))
            for index, name in enumerate(FEATURES)
        },
        approximate=True,
    )


def _history(tile: str, count: int = 0) -> fhf.FireHistoryFeatures:
    return fhf.FireHistoryFeatures(
        tile_id=tile,
        cutoff=CUTOFF,
        previous_24h_count=count,
        previous_72h_count=count,
        previous_7d_count=count,
        previous_30d_count=count,
        neighboring_previous_24h_count=0,
    )


@pytest.mark.parametrize(
    ("now", "expected_day"),
    [
        (datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc), 10),
        (datetime(2026, 11, 10, 10, 10, tzinfo=timezone.utc), 9),
        (datetime(2026, 11, 10, 2, 0, tzinfo=timezone.utc), 9),
    ],
)
def test_daily_cutoff_waits_until_the_morning_data_is_ready(now, expected_day) -> None:
    cutoff = daily_cutoff(now)
    assert cutoff.hour == 10 and cutoff.day == expected_day
    assert cutoff <= now


def test_cell_geography_round_trips(tmp_path) -> None:
    geography = {"CA_0001_0002": CellGeography(812.34, 7.891, 30)}
    path = save_cell_geography(geography, tmp_path / "cells.csv")
    expected = {"CA_0001_0002": CellGeography(812.3, 7.89, 30)}
    assert load_cell_geography(path) == expected


def test_map_rows_skip_water_and_unknown_cells() -> None:
    cells = build_california_grid()[:3]
    geography = {
        cells[0].tile_id: CellGeography(100.0, 2.0, 30),
        cells[1].tile_id: CellGeography(0.0, 0.0, 80),
    }
    history = {cell.tile_id: _history(cell.tile_id, 2) for cell in cells}

    rows = map_rows(cells, geography, history, _forecast(), 2)

    assert [row.tile_id for row in rows] == [cells[0].tile_id]
    assert rows[0].lead_day == 2
    assert rows[0].previous_7d_count == 2
    assert rows[0].forecast_hdw_max == pytest.approx(10.0)
    assert rows[0].forecast_t2m_max == pytest.approx(40.0)


def test_risk_payload_lists_each_day_in_tile_order(monkeypatch) -> None:
    cells = build_california_grid()[:4]
    geography = {cell.tile_id: CellGeography(100.0, 2.0, 30) for cell in cells}
    history = {cell.tile_id: _history(cell.tile_id) for cell in cells}
    forecast = _forecast()
    rows = {
        lead: map_rows(cells, geography, history, forecast, lead)
        for lead in (1, 2, 3)
    }
    monkeypatch.setattr(
        "ai_earth_intelligence_and_forecasting_engine.earth2.daily_map.predict",
        lambda model, rows: np.full(len(rows), model["value"]),
    )
    models = {lead: {"value": lead / 100} for lead in (1, 2, 3)}

    payload = risk_payload(forecast, models, rows, {"version": "e7_v1"})

    assert payload["tiles"] == [cell.tile_id for cell in cells]
    assert [lead["risk"][0] for lead in payload["leads"]] == [0.01, 0.02, 0.03]
    assert payload["leads"][2]["to"] == "2026-11-13T10:00:00+00:00"
    assert payload["forecast_start"] == "2026-11-10T06:00:00+00:00"


def test_run_log_keeps_one_entry_per_cutoff() -> None:
    runs = [{"cutoff": str(day), "status": "succeeded"} for day in range(40)]
    updated = update_runs(runs, {"cutoff": "39", "status": "failed"})
    assert len(updated) == 30
    assert updated[-1] == {"cutoff": "39", "status": "failed"}
    assert [run["cutoff"] for run in updated].count("39") == 1
