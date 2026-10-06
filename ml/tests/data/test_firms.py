from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
import requests

from ai_earth_intelligence_and_forecasting_engine.data.firms import (
    FIRMSConfig,
    FIRMSRecord,
    fetch_firms_sample,
    load_firms_config,
    normalize_firms_record,
    parse_firms_records,
)


def test_firms_config_default_product():
    config = FIRMSConfig(map_key="test-key")

    assert config.product == "VIIRS_SNPP_SP"

def test_firms_config_requires_map_key(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FIRMS_MAP_KEY"):
        load_firms_config()

def test_parse_valid_firms_record():
    csv_text = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    "satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
    "40.82067,-114.25546,314.77,0.42,0.46,2024-08-15,1001,"
    "N,VIIRS,n,2,289.63,2.04,N,2\n"
    )

    records = parse_firms_records(csv_text)

    assert len(records) == 1

    record = records[0]

    assert record.latitude == 40.82067
    assert record.longitude == -114.25546
    assert record.observed_at == datetime(
        2024,
        8,
        15,
        10,
        1,
        tzinfo=timezone.utc,
    )
    assert record.source_record["satellite"] == "N"
    assert record.source_record["frp"] == "2.04"

def test_parse_firms_record_rejects_invalid_coordinate():
    csv_text = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
        "satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
        "91.0,-114.25546,314.77,0.42,0.46,2024-08-15,1001,"
        "N,VIIRS,n,2,289.63,2.04,N,2\n"
    )

    with pytest.raises(ValueError, match="Invalid latitude"):
        parse_firms_records(csv_text)

def test_parse_firms_record_rejects_invalid_timestamp():
    csv_text = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
        "satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
        "40.82067,-114.25546,314.77,0.42,0.46,2024-08-15,2561,"
        "N,VIIRS,n,2,289.63,2.04,N,2\n"
    )

    with pytest.raises(ValueError):
        parse_firms_records(csv_text)

def test_parse_firms_record_rejects_missing_required_field():
    csv_text = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,"
        "satellite,instrument,confidence,version,bright_ti5,frp,daynight,type\n"
        "40.82067,-114.25546,314.77,0.42,0.46,2024-08-15,"
        "N,VIIRS,n,2,289.63,2.04,N,2\n"
    )

    with pytest.raises(
        ValueError,
        match="missing required fields",
    ):
        parse_firms_records(csv_text)

def test_fetch_firms_sample_handles_provider_failure(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    output_path = tmp_path / "firms.csv"

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.requests.get"
        ) as mock_get,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.time.sleep"
        ) as mock_sleep,
    ):
        mock_get.side_effect = requests.ConnectionError(
            "provider unavailable"
        )

        with pytest.raises(
            requests.ConnectionError,
            match="provider unavailable",
        ):
            fetch_firms_sample(
                config=config,
                bbox=(-124.5, 32.5, -114.0, 42.0),
                observed_date=date(2024, 8, 15),
                output_path=output_path,
            )

    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2

def test_fetch_firms_sample_retries_then_succeeds(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    output_path = tmp_path / "firms.csv"

    csv_text = """latitude,longitude,acq_date,acq_time
40.82067,-114.25546,2024-08-15,1001
"""

    mock_response = requests.Response()
    mock_response.status_code = 200
    mock_response._content = csv_text.encode("utf-8")

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.requests.get"
        ) as mock_get,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.time.sleep"
        ) as mock_sleep,
    ):
        mock_get.side_effect = [
            requests.ConnectionError("temporary failure"),
            mock_response,
        ]

        result = fetch_firms_sample(
            config=config,
            bbox=(-124.5, 32.5, -114.0, 42.0),
            observed_date=date(2024, 8, 15),
            output_path=output_path,
        )

    assert result == output_path
    assert output_path.exists()
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1

def test_fetch_firms_sample_retries_on_rate_limit(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    output_path = tmp_path / "firms.csv"

    response = requests.Response()
    response.status_code = 429
    response._content = b"rate limited"

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.requests.get"
        ) as mock_get,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.time.sleep"
        ) as mock_sleep,
    ):
        mock_get.return_value = response

        with pytest.raises(requests.HTTPError):
            fetch_firms_sample(
                config=config,
                bbox=(-124.5, 32.5, -114.0, 42.0),
                observed_date=date(2024, 8, 15),
                output_path=output_path,
            )

    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2

def test_fetch_firms_sample_retries_on_server_error(tmp_path):
    config = FIRMSConfig(map_key="test-key")
    output_path = tmp_path / "firms.csv"

    response = requests.Response()
    response.status_code = 500
    response._content = b"server error"

    with (
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.requests.get"
        ) as mock_get,
        patch(
            "ai_earth_intelligence_and_forecasting_engine.data.firms.time.sleep"
        ) as mock_sleep,
    ):
        mock_get.return_value = response

        with pytest.raises(requests.HTTPError):
            fetch_firms_sample(
                config=config,
                bbox=(-124.5, 32.5, -114.0, 42.0),
                observed_date=date(2024, 8, 15),
                output_path=output_path,
            )

    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2

def test_normalize_firms_record_to_observation():
    record = FIRMSRecord(
        latitude=40.82067,
        longitude=-114.25546,
        observed_at=datetime(
            2024,
            8,
            15,
            10,
            1,
            tzinfo=timezone.utc,
        ),
        source_record={
            "confidence": "n",
            "frp": "2.04",
            "satellite": "N",
        },
    )

    ingested_at = datetime(
        2026,
        9,
        19,
        12,
        0,
        tzinfo=timezone.utc,
    )

    observation = normalize_firms_record(
        record=record,
        product="VIIRS_SNPP_SP",
        source_record_id="firms-001",
        ingested_at=ingested_at,
    )

    assert observation.observation_id == "firms:firms-001"
    assert observation.source == "NASA_FIRMS"
    assert observation.product == "VIIRS_SNPP_SP"
    assert observation.observed_at == record.observed_at
    assert observation.latitude == record.latitude
    assert observation.longitude == record.longitude
    assert observation.source_record_id == "firms-001"
    assert observation.ingested_at == ingested_at
    assert observation.confidence == "n"
