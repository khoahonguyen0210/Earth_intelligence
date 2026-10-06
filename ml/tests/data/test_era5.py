from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import xarray as xr

from ai_earth_intelligence_and_forecasting_engine.data.era5 import (
    ERA5Config,
    ERA5Record,
    build_area,
    fetch_era5_sample,
    load_era5_config,
    parse_era5_records,
    relative_humidity_percent,
)

REAL_ERA5_PATH = Path("data/raw/era5/history/era5_land_2020_08.nc")


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


def _parse_era5_records_row_by_row(nc_path) -> list[ERA5Record]:
    dataset = xr.open_dataset(nc_path)
    frame = dataset.to_dataframe().reset_index()
    records = []

    for _, row in frame.iterrows():
        valid_time = row["valid_time"] if "valid_time" in row else row["time"]
        valid_time = (
            valid_time.to_pydatetime()
            if hasattr(valid_time, "to_pydatetime")
            else valid_time
        )
        records.append(
            ERA5Record(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                valid_time=valid_time.replace(tzinfo=timezone.utc),
                temperature_2m=float(row["t2m"]),
                total_precipitation=float(row["tp"]),
                u_wind_10m=float(row["u10"]),
                v_wind_10m=float(row["v10"]),
                dewpoint_2m=float(row["d2m"]),
                source_record={
                    name: str(row[name]) for name in ("t2m", "tp", "u10", "v10", "d2m")
                },
            )
        )

    dataset.close()
    return records


def test_parse_era5_records_matches_the_row_by_row_parser(tmp_path):
    nc_path = tmp_path / "era5_grid.nc"
    shape = (2, 3, 4)
    rng = np.random.default_rng(0)
    variables = {
        name: (
            ["valid_time", "latitude", "longitude"],
            rng.normal(loc, scale, size=shape).astype(np.float32),
        )
        for name, loc, scale in (
            ("t2m", 295.0, 5.0),
            ("tp", 0.001, 0.0005),
            ("u10", 0.0, 3.0),
            ("v10", 0.0, 3.0),
            ("d2m", 285.0, 5.0),
        )
    }
    variables["t2m"][1][0, 1, 2] = np.nan
    dataset = xr.Dataset(
        variables,
        coords={
            "valid_time": [
                np.datetime64("2024-08-15T10:00:00"),
                np.datetime64("2024-08-16T10:00:00"),
            ],
            "latitude": [38.0, 37.9, 37.8],
            "longitude": [-120.3, -120.2, -120.1, -120.0],
        },
    )
    dataset.to_netcdf(nc_path)
    dataset.close()

    assert _same_records(
        parse_era5_records(nc_path), _parse_era5_records_row_by_row(nc_path)
    )


@pytest.mark.skipif(
    not REAL_ERA5_PATH.exists(), reason="real ERA5 history not downloaded"
)
def test_parse_era5_records_matches_the_row_by_row_parser_on_real_data(tmp_path):
    nc_path = tmp_path / "era5_real_slice.nc"
    with xr.open_dataset(REAL_ERA5_PATH) as dataset:
        dataset.isel(valid_time=slice(0, 2)).to_netcdf(nc_path)

    fast = parse_era5_records(nc_path)

    assert len(fast) > 0
    assert _same_records(fast, _parse_era5_records_row_by_row(nc_path))


def _same_records(left: list[ERA5Record], right: list[ERA5Record]) -> bool:
    def key(record: ERA5Record) -> tuple:
        return (
            record.latitude,
            record.longitude,
            record.valid_time,
            repr(record.temperature_2m),
            repr(record.total_precipitation),
            repr(record.u_wind_10m),
            repr(record.v_wind_10m),
            repr(record.dewpoint_2m),
            tuple(sorted(record.source_record.items())),
        )

    return [key(r) for r in left] == [key(r) for r in right]
