from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)
from moto import mock_aws

from ai_earth_intelligence_and_forecasting_engine.storage.s3 import (
    ArtifactStore,
    ObjectNotFound,
    S3Settings,
    StorageError,
    describe_error,
    require_safe_key,
    sha256_of,
)

BUCKET = "ai-earth-test-artifacts"


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    for name in ("ARTIFACT_BUCKET", "AWS_REGION", "S3_ENDPOINT_URL", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def store(aws_env: None):
    with mock_aws():
        client = boto3.client("s3", region_name="us-west-2")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "us-west-2"},
        )
        yield ArtifactStore(client, BUCKET)


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_settings_are_disabled_without_a_bucket(aws_env: None) -> None:
    assert S3Settings.from_env() is None
    assert ArtifactStore.from_env() is None


def test_settings_read_bucket_region_and_endpoint(
    aws_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARTIFACT_BUCKET", BUCKET)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")

    assert S3Settings.from_env() == S3Settings(
        bucket=BUCKET, region="eu-west-1", endpoint_url="http://localhost:9000"
    )


def test_upload_then_download_round_trips_with_checksum(
    store: ArtifactStore, tmp_path: Path
) -> None:
    source = _write(tmp_path / "model.json", b'{"version": "v1"}')

    uploaded = store.upload_file(source, "ml/models/v1/model.json")
    downloaded = store.download_file(
        "ml/models/v1/model.json", tmp_path / "out" / "model.json"
    )

    assert uploaded.sha256 == sha256_of(source)
    assert downloaded == uploaded
    assert (tmp_path / "out" / "model.json").read_bytes() == source.read_bytes()


def test_upload_stores_checksum_metadata(store: ArtifactStore, tmp_path: Path) -> None:
    source = _write(tmp_path / "data.csv", b"a,b\n1,2\n")

    store.upload_file(source, "ml/datasets/data.csv")
    head = store.client.head_object(Bucket=BUCKET, Key="ml/datasets/data.csv")

    assert head["Metadata"]["sha256"] == sha256_of(source)


def test_upload_rejects_missing_local_file(
    store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(StorageError, match="local file does not exist"):
        store.upload_file(tmp_path / "missing.csv", "ml/datasets/missing.csv")


def test_download_of_missing_key_raises_not_found(
    store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(ObjectNotFound, match="object not found"):
        store.download_file("ml/models/none/model.json", tmp_path / "model.json")
    assert not (tmp_path / "model.json").exists()


def test_corrupt_download_is_discarded_and_keeps_existing_file(
    store: ArtifactStore, tmp_path: Path
) -> None:
    store.client.put_object(
        Bucket=BUCKET,
        Key="ml/models/v1/model.json",
        Body=b"tampered",
        Metadata={"sha256": "0" * 64},
    )
    target = _write(tmp_path / "model.json", b"good copy")

    with pytest.raises(StorageError, match="checksum mismatch"):
        store.download_file("ml/models/v1/model.json", target)

    assert target.read_bytes() == b"good copy"
    assert list(tmp_path.iterdir()) == [target]


def test_missing_bucket_is_reported(aws_env: None) -> None:
    with mock_aws():
        missing = ArtifactStore(boto3.client("s3", region_name="us-west-2"), "nope")
        with pytest.raises(StorageError, match="bucket does not exist"):
            missing.check_bucket()


def test_check_bucket_passes_for_existing_bucket(store: ArtifactStore) -> None:
    store.check_bucket()


def test_exists(store: ArtifactStore, tmp_path: Path) -> None:
    store.upload_file(_write(tmp_path / "a.txt", b"a"), "ml/a.txt")

    assert store.exists("ml/a.txt")
    assert not store.exists("ml/b.txt")


def test_directory_round_trip_keeps_nested_layout(
    store: ArtifactStore, tmp_path: Path
) -> None:
    source = tmp_path / "v1"
    _write(source / "model.json", b"model")
    _write(source / "calibration" / "isotonic.json", b"iso")

    uploaded = store.upload_dir(source, "ml/models/v1/")
    written = store.download_dir("ml/models/v1", tmp_path / "copy")

    assert [item.key for item in uploaded] == [
        "ml/models/v1/calibration/isotonic.json",
        "ml/models/v1/model.json",
    ]
    assert sorted(
        path.relative_to(tmp_path / "copy").as_posix() for path in written
    ) == [
        "calibration/isotonic.json",
        "model.json",
    ]
    assert (tmp_path / "copy" / "calibration" / "isotonic.json").read_bytes() == b"iso"


def test_download_dir_does_not_match_sibling_prefixes(
    store: ArtifactStore, tmp_path: Path
) -> None:
    store.upload_file(_write(tmp_path / "a", b"1"), "ml/models/v1/a")
    store.upload_file(_write(tmp_path / "b", b"2"), "ml/models/v10/b")

    written = store.download_dir("ml/models/v1", tmp_path / "copy")

    assert [path.name for path in written] == ["a"]


def test_download_dir_with_no_objects_raises(
    store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(StorageError, match="no objects found"):
        store.download_dir("ml/models/none", tmp_path)


def test_upload_dir_rejects_missing_and_empty_directories(
    store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(StorageError, match="does not exist"):
        store.upload_dir(tmp_path / "missing", "ml/x")
    (tmp_path / "empty").mkdir()
    with pytest.raises(StorageError, match="is empty"):
        store.upload_dir(tmp_path / "empty", "ml/x")


@pytest.mark.parametrize(
    "key", ["", "/abs/key", "ml/../secret", "ml//double", "ml/./here", "ml\\win"]
)
def test_unsafe_keys_are_rejected(key: str) -> None:
    with pytest.raises(StorageError):
        require_safe_key(key)


def test_long_keys_are_rejected() -> None:
    with pytest.raises(StorageError):
        require_safe_key("a" * 1025)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "HeadObject")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (NoCredentialsError(), "no AWS credentials found"),
        (EndpointConnectionError(endpoint_url="http://x"), "cannot reach"),
        (_client_error("NoSuchBucket"), "bucket does not exist"),
        (_client_error("AccessDenied"), "access denied"),
        (_client_error("403"), "access denied"),
        (_client_error("SlowDown"), "S3 error SlowDown"),
    ],
)
def test_errors_are_described(error: Exception, message: str) -> None:
    described = describe_error(error, "upload", "s3://bucket/key")

    assert message in str(described)
    assert str(described).startswith("upload s3://bucket/key")


def test_not_found_errors_use_their_own_type() -> None:
    assert isinstance(describe_error(_client_error("404"), "read", "k"), ObjectNotFound)
