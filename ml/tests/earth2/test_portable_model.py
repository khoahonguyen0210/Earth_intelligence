import json
from datetime import datetime, timezone

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.earth2.e7 import (
    E7_FEATURES,
    E7Row,
    fit_lead_model,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.portable import (
    export_model,
    predict,
)
from ai_earth_intelligence_and_forecasting_engine.models.calibration import (
    predict_calibrated,
)


def _rows(year: int, count: int, seed: int) -> list[E7Row]:
    rng = np.random.default_rng(seed)
    cutoff = datetime(year, 8, 6, 10, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        signal = rng.random()
        fire = int(signal > 0.9)
        rows.append(
            E7Row(
                tile_id=f"t{index}",
                cutoff=cutoff,
                split="train",
                target=fire,
                previous_24h_count=int(fire and rng.random() < 0.5),
                previous_72h_count=int(rng.random() < 0.1),
                previous_7d_count=int(rng.integers(0, 3)),
                previous_30d_count=int(rng.integers(0, 6)),
                neighboring_previous_24h_count=0,
                temperature_2m=None,
                total_precipitation=None,
                u_wind_10m=None,
                v_wind_10m=None,
                relative_humidity=None,
                elevation_m=None if index % 17 == 0 else float(rng.random() * 2000),
                slope_deg=float(rng.random() * 30),
                land_cover_class=int(rng.choice([10, 20, 30, 0])),
                lead_day=1,
                forecast_hdw_max=signal * 200,
                forecast_wind_max=None if index % 13 == 0 else signal * 15,
                forecast_vpd_max=signal * 20,
                forecast_t2m_max=290 + signal * 20,
            )
        )
    return rows


def test_exported_model_matches_the_calibrated_model() -> None:
    model = fit_lead_model(_rows(2020, 1500, 1), _rows(2023, 700, 2), E7_FEATURES)
    test = _rows(2025, 400, 3)

    exported = json.loads(json.dumps(export_model(model)))

    assert np.allclose(
        predict(exported, test), predict_calibrated(model, test), atol=1e-6
    )


def test_unknown_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="format"):
        predict({"format_version": 99}, [])
