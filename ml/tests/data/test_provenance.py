import hashlib
import json
from datetime import date, datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.data.provenance import (
    build_provenance,
    compute_file_checksum,
    get_pipeline_version,
    provenance_to_dict,
    save_provenance,
)


def test_get_pipeline_version_returns_nonempty_string():
    assert isinstance(get_pipeline_version(), str)
    assert get_pipeline_version() != ""


def test_compute_file_checksum_matches_known_sha256(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_bytes(b"hello world")

    expected = hashlib.sha256(b"hello world").hexdigest()

    assert compute_file_checksum(file_path) == expected


def test_compute_file_checksum_differs_for_different_content(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_bytes(b"content a")
    file_b.write_bytes(b"content b")

    assert compute_file_checksum(file_a) != compute_file_checksum(file_b)


def test_build_provenance_without_raw_file_has_no_checksum():
    record = build_provenance(
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        dataset_version="VIIRS_SNPP_SP-standard-processing",
        period_start=datetime(2024, 8, 15, tzinfo=timezone.utc),
        period_end=datetime(2024, 8, 16, tzinfo=timezone.utc),
        retrieval_timestamp=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )

    assert record.source == "NASA_FIRMS"
    assert record.checksum is None
    assert record.checksum_algorithm is None
    assert record.period_start == "2024-08-15T00:00:00+00:00"
    assert record.retrieval_timestamp == "2026-09-20T00:00:00+00:00"


def test_build_provenance_with_raw_file_computes_checksum(tmp_path):
    raw_path = tmp_path / "raw.csv"
    raw_path.write_bytes(b"latitude,longitude\n1,2\n")

    record = build_provenance(
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        dataset_version="VIIRS_SNPP_SP-standard-processing",
        raw_file_path=raw_path,
    )

    assert record.checksum == compute_file_checksum(raw_path)
    assert record.checksum_algorithm == "sha256"


def test_build_provenance_defaults_retrieval_timestamp_to_now():
    before = datetime.now(timezone.utc)

    record = build_provenance(
        source="ECMWF_CDS",
        product="reanalysis-era5-land",
        dataset_version="reanalysis-era5-land",
    )

    after = datetime.now(timezone.utc)
    retrieved = datetime.fromisoformat(record.retrieval_timestamp)

    assert before <= retrieved <= after


def test_provenance_to_dict_is_json_serializable():
    record = build_provenance(
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        dataset_version="VIIRS_SNPP_SP-standard-processing",
        parameters={
            "bbox": [-124.5, 32.5, -114.0, 42.0],
            "day": str(date(2024, 8, 15)),
        },
    )

    payload = provenance_to_dict(record)
    json.dumps(payload)

    assert payload["parameters"]["bbox"] == [-124.5, 32.5, -114.0, 42.0]


def test_save_provenance_roundtrip(tmp_path):
    record = build_provenance(
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        dataset_version="VIIRS_SNPP_SP-standard-processing",
    )

    output_path = tmp_path / "provenance.json"
    result = save_provenance(record, output_path)

    saved = json.loads(result.read_text(encoding="utf-8"))

    assert saved["source"] == "NASA_FIRMS"
    assert saved["pipeline_version"] == get_pipeline_version()
