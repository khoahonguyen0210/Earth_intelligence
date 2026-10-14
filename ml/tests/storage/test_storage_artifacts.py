from __future__ import annotations

import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    ModelRegistry,
)
from ai_earth_intelligence_and_forecasting_engine.storage.artifacts import (
    dataset_files,
    pull_datasets,
    pull_model_version,
    pull_registry,
    push_datasets,
    push_model_version,
)
from ai_earth_intelligence_and_forecasting_engine.storage.s3 import (
    ArtifactStore,
    StorageError,
)

BUCKET = "ai-earth-test-artifacts"


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield ArtifactStore(client, BUCKET)


def _registry_with_version(root: Path, version: str) -> ModelRegistry:
    directory = root / "versions" / version
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(json.dumps({"version": version}))
    (directory / "model.json").write_text("{}")
    root.joinpath("registry.json").write_text(
        json.dumps({"current": version, "promotions": [], "runs": []})
    )
    return ModelRegistry(root)


def test_dataset_files_pick_csv_and_manifests_only(tmp_path: Path) -> None:
    for name in (
        "historical_dataset_v1.csv",
        "historical_dataset_v1.manifest.json",
        "historical_dataset_2025.csv",
        "build_2025.log",
    ):
        (tmp_path / name).write_text("x")

    assert [path.name for path in dataset_files(tmp_path)] == [
        "historical_dataset_2025.csv",
        "historical_dataset_v1.csv",
        "historical_dataset_v1.manifest.json",
    ]


def test_datasets_round_trip(store: ArtifactStore, tmp_path: Path) -> None:
    source = tmp_path / "processed"
    source.mkdir()
    (source / "historical_dataset_v1.csv").write_text("tile_id,target\nCA_1,0\n")
    (source / "historical_dataset_v1.manifest.json").write_text('{"rows": 1}')

    uploaded = push_datasets(store, source)
    written = pull_datasets(store, tmp_path / "restored")

    assert [item.key for item in uploaded] == [
        "ml/datasets/historical_dataset_v1.csv",
        "ml/datasets/historical_dataset_v1.manifest.json",
    ]
    assert sorted(path.name for path in written) == [
        "historical_dataset_v1.csv",
        "historical_dataset_v1.manifest.json",
    ]


def test_push_datasets_without_files_raises(
    store: ArtifactStore, tmp_path: Path
) -> None:
    with pytest.raises(StorageError, match="no historical datasets"):
        push_datasets(store, tmp_path)


def test_model_version_and_registry_round_trip(
    store: ArtifactStore, tmp_path: Path
) -> None:
    registry = _registry_with_version(tmp_path / "local", "season2025-1")

    stored = push_model_version(store, registry, "season2025-1")
    remote = pull_registry(store, tmp_path / "remote")
    directory = pull_model_version(store, tmp_path / "remote", "season2025-1")

    assert stored[-1].key == "ml/registry/registry.json"
    assert remote.current == "season2025-1"
    assert json.loads((directory / "metadata.json").read_text()) == {
        "version": "season2025-1"
    }


def test_push_unknown_version_raises(store: ArtifactStore, tmp_path: Path) -> None:
    registry = _registry_with_version(tmp_path / "local", "v1")

    with pytest.raises(StorageError, match="version is not in"):
        push_model_version(store, registry, "v2")
    assert store.list_keys("ml/") == []
