from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    ERA5Config,
    build_area,
    fetch_era5_sample,
    load_era5_config,
    parse_era5_records,
    relative_humidity_percent,
)


def test_era5_config_default_dataset():
    config = ERA5Config(url="https://example.test", key="test-key")

    assert config.dataset == "reanalysis-era5-land"
    assert "2m_temperature" in config.variables


def test_era5_config_requires_url(monkeypatch):
    monkeypatch.delenv("CDSAPI_URL", raising=False)
    monkeypatch.setenv("CDSAPI_KEY", "test-key")

    with pytest.raises(RuntimeError, match="CDSAPI_URL"):
        load_era5_config()


def test_era5_config_requires_key(monkeypatch):
    monkeypatch.setenv("CDSAPI_URL", "https://example.test")
    monkeypatch.delenv("CDSAPI_KEY", raising=False)

    with pytest.raises(RuntimeError, match="CDSAPI_KEY"):
        load_era5_config()


def test_build_area_orders_north_west_south_east():
    bbox = (-124.5, 32.5, -114.0, 42.0)

    assert build_area(bbox) == [42.0, -124.5, 32.5, -114.0]


def _write_sample_netcdf(path) -> None:
    dataset = xr.Dataset(
        {
            "t2m": (["valid_time", "latitude", "longitude"], np.array([[[295.0]]])),
            "tp": (["valid_time", "latitude", "longitude"], np.array([[[0.001]]])),
            "u10": (["valid_time", "latitude", "longitude"], np.array([[[1.5]]])),
            "v10": (["valid_time", "latitude", "longitude"], np.array([[[-0.5]]])),
            "d2m": (["valid_time", "latitude", "longitude"], np.array([[[289.0]]])),
        },
        coords={
            "valid_time": [np.datetime64("2024-08-15T10:00:00")],
            "latitude": [37.5],
            "longitude": [-120.5],
        },
    )
    dataset.to_netcdf(path)
    dataset.close()


def test_parse_valid_era5_record(tmp_path):
    nc_path = tmp_path / "era5.nc"
    _write_sample_netcdf(nc_path)

    records = parse_era5_records(nc_path)

    assert len(records) == 1

    record = records[0]

    assert record.latitude == 37.5
    assert record.longitude == -120.5
    assert record.valid_time == datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)
    assert record.temperature_2m == pytest.approx(295.0)
    assert record.total_precipitation == pytest.approx(0.001)
    assert record.u_wind_10m == pytest.approx(1.5)
    assert record.v_wind_10m == pytest.approx(-0.5)
    assert record.dewpoint_2m == pytest.approx(289.0)


def test_parse_era5_records_rejects_missing_variable(tmp_path):
    nc_path = tmp_path / "era5_missing.nc"

    dataset = xr.Dataset(
        {
            "t2m": (["valid_time", "latitude", "longitude"], np.array([[[295.0]]])),
        },
        coords={
            "valid_time": [np.datetime64("2024-08-15T10:00:00")],
            "latitude": [37.5],
            "longitude": [-120.5],
        },
    )
    dataset.to_netcdf(nc_path)
    dataset.close()

    with pytest.raises(ValueError, match="missing required variables"):
        parse_era5_records(nc_path)


def test_fetch_era5_sample_calls_client_retrieve(tmp_path):
    config = ERA5Config(url="https://example.test", key="test-key")
    output_path = tmp_path / "era5.nc"

    mock_client = MagicMock()

    with patch(
        "ai_earth_intelligence_and_forecasting_engine.data.era5.cdsapi.Client",
        return_value=mock_client,
    ) as mock_client_cls:
        result = fetch_era5_sample(
            config=config,
            bbox=(-124.5, 32.5, -114.0, 42.0),
            observed_date=date(2024, 8, 15),
            hour="10:00",
            output_path=output_path,
        )

    mock_client_cls.assert_called_once_with(
        url="https://example.test", key="test-key"
    )
    mock_client.retrieve.assert_called_once()

    call_args = mock_client.retrieve.call_args
    assert call_args[0][0] == "reanalysis-era5-land"

    request = call_args[0][1]
    assert request["year"] == "2024"
    assert request["month"] == "08"
    assert request["day"] == "15"
    assert request["time"] == "10:00"
    assert request["area"] == [42.0, -124.5, 32.5, -114.0]

    assert result == output_path


def test_relative_humidity_percent_saturated_is_100():
    assert relative_humidity_percent(288.0, 288.0) == pytest.approx(100.0)


def test_relative_humidity_percent_drier_air_is_lower():
    saturated = relative_humidity_percent(295.0, 295.0)
    drier = relative_humidity_percent(295.0, 280.0)

    assert drier < saturated
