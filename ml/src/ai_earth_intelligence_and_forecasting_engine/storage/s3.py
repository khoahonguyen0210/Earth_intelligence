from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

CHECKSUM_KEY = "sha256"
MAX_KEY_BYTES = 1024
CHUNK_BYTES = 1024 * 1024
DEFAULT_REGION = "us-west-2"
NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
ACCESS_DENIED_CODES = {"403", "AccessDenied", "Forbidden"}


class StorageError(Exception):
    pass


class ObjectNotFound(StorageError):
    pass


@dataclass(frozen=True)
class S3Settings:
    bucket: str
    region: str = DEFAULT_REGION
    endpoint_url: str | None = None

    @classmethod
    def from_env(cls) -> S3Settings | None:
        bucket = os.environ.get("ARTIFACT_BUCKET", "").strip()
        if not bucket:
            return None
        return cls(
            bucket=bucket,
            region=os.environ.get("AWS_REGION", "").strip() or DEFAULT_REGION,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", "").strip() or None,
        )


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_safe_key(key: str) -> str:
    if not key or len(key.encode("utf-8")) > MAX_KEY_BYTES:
        raise StorageError(f"object key must be 1 to {MAX_KEY_BYTES} bytes: {key!r}")
    if key.startswith("/") or "\\" in key:
        raise StorageError(f"object key must be a relative posix path: {key!r}")
    if any(part in ("", ".", "..") for part in key.split("/")):
        raise StorageError(f"object key has an unsafe segment: {key!r}")
    return key


def describe_error(error: Exception, action: str, target: str) -> StorageError:
    if isinstance(error, NoCredentialsError):
        return StorageError(
            f"{action} {target}: no AWS credentials found; set AWS_ACCESS_KEY_ID "
            "and AWS_SECRET_ACCESS_KEY or configure an AWS profile"
        )
    if isinstance(error, EndpointConnectionError):
        return StorageError(f"{action} {target}: cannot reach the S3 endpoint")
    if isinstance(error, ClientError):
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code == "NoSuchBucket":
            return StorageError(f"{action} {target}: bucket does not exist")
        if code in NOT_FOUND_CODES:
            return ObjectNotFound(f"{action} {target}: object not found")
        if code in ACCESS_DENIED_CODES:
            return StorageError(f"{action} {target}: access denied")
        return StorageError(f"{action} {target}: S3 error {code or 'unknown'}")
    if isinstance(error, BotoCoreError):
        return StorageError(f"{action} {target}: {error}")
    return StorageError(f"{action} {target}: {error}")


class ArtifactStore:
    def __init__(self, client: Any, bucket: str):
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_settings(cls, settings: S3Settings) -> ArtifactStore:
        client = boto3.client(
            "s3",
            region_name=settings.region,
            endpoint_url=settings.endpoint_url,
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=3,
                read_timeout=60,
            ),
        )
        return cls(client, settings.bucket)

    @classmethod
    def from_env(cls) -> ArtifactStore | None:
        settings = S3Settings.from_env()
        return cls.from_settings(settings) if settings else None

    def _uri(self, key: str = "") -> str:
        return f"s3://{self.bucket}/{key}"

    def check_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in NOT_FOUND_CODES:
                raise StorageError(f"check {self._uri()}: bucket does not exist")
            raise describe_error(error, "check", self._uri()) from error
        except BotoCoreError as error:
            raise describe_error(error, "check", self._uri()) from error

    def head(self, key: str) -> StoredObject:
        require_safe_key(key)
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as error:
            raise describe_error(error, "read", self._uri(key)) from error
        return StoredObject(
            key=key,
            size=int(response["ContentLength"]),
            sha256=response.get("Metadata", {}).get(CHECKSUM_KEY, ""),
        )

    def exists(self, key: str) -> bool:
        try:
            self.head(key)
        except ObjectNotFound:
            return False
        return True

    def upload_file(self, path: Path, key: str) -> StoredObject:
        require_safe_key(key)
        if not path.is_file():
            raise StorageError(f"upload {path}: local file does not exist")
        size = path.stat().st_size
        checksum = sha256_of(path)
        try:
            self.client.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={"Metadata": {CHECKSUM_KEY: checksum}},
            )
        except (ClientError, BotoCoreError) as error:
            raise describe_error(error, "upload", self._uri(key)) from error
        stored = self.head(key)
        if stored.size != size or stored.sha256 != checksum:
            raise StorageError(
                f"upload {self._uri(key)}: stored object does not match {path}"
            )
        return stored

    def download_file(self, key: str, path: Path) -> StoredObject:
        stored = self.head(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f".{path.name}.part")
        try:
            self.client.download_file(self.bucket, key, str(partial))
        except (ClientError, BotoCoreError) as error:
            partial.unlink(missing_ok=True)
            raise describe_error(error, "download", self._uri(key)) from error
        size = partial.stat().st_size
        checksum = sha256_of(partial)
        if size != stored.size or (stored.sha256 and checksum != stored.sha256):
            partial.unlink(missing_ok=True)
            raise StorageError(
                f"download {self._uri(key)}: checksum mismatch, file discarded"
            )
        os.replace(partial, path)
        return StoredObject(key=key, size=size, sha256=checksum)

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                keys.extend(item["Key"] for item in page.get("Contents", []))
        except (ClientError, BotoCoreError) as error:
            raise describe_error(error, "list", self._uri(prefix)) from error
        return sorted(keys)

    def upload_dir(self, directory: Path, prefix: str) -> list[StoredObject]:
        if not directory.is_dir():
            raise StorageError(f"upload {directory}: local directory does not exist")
        files = sorted(path for path in directory.rglob("*") if path.is_file())
        if not files:
            raise StorageError(f"upload {directory}: directory is empty")
        base = prefix.rstrip("/")
        return [
            self.upload_file(path, f"{base}/{path.relative_to(directory).as_posix()}")
            for path in files
        ]

    def download_dir(self, prefix: str, directory: Path) -> list[Path]:
        base = prefix.rstrip("/") + "/"
        keys = self.list_keys(base)
        if not keys:
            raise StorageError(f"download {self._uri(base)}: no objects found")
        written = []
        for key in keys:
            if key.endswith("/"):
                continue
            relative = PurePosixPath(require_safe_key(key)[len(base) :])
            target = directory.joinpath(*relative.parts)
            self.download_file(key, target)
            written.append(target)
        return written
