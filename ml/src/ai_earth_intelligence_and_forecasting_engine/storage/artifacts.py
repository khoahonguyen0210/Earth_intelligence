from __future__ import annotations

from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    REGISTRY_FILE,
    VERSIONS_DIR,
    ModelRegistry,
)
from ai_earth_intelligence_and_forecasting_engine.storage.s3 import (
    ArtifactStore,
    StorageError,
    StoredObject,
)

DATASETS_PREFIX = "ml/datasets"
MODELS_PREFIX = "ml/models"
REGISTRY_PREFIX = "ml/registry"
DATASET_PATTERNS = ("historical_dataset_*.csv", "historical_dataset_*.manifest.json")


def dataset_key(name: str) -> str:
    return f"{DATASETS_PREFIX}/{name}"


def model_prefix(version: str) -> str:
    return f"{MODELS_PREFIX}/{version}"


def registry_key(name: str = REGISTRY_FILE) -> str:
    return f"{REGISTRY_PREFIX}/{name}"


def dataset_files(directory: Path) -> list[Path]:
    return sorted(
        {path for pattern in DATASET_PATTERNS for path in directory.glob(pattern)}
    )


def push_datasets(store: ArtifactStore, directory: Path) -> list[StoredObject]:
    files = dataset_files(directory)
    if not files:
        raise StorageError(f"upload {directory}: no historical datasets found")
    return [store.upload_file(path, dataset_key(path.name)) for path in files]


def pull_datasets(store: ArtifactStore, directory: Path) -> list[Path]:
    return store.download_dir(DATASETS_PREFIX, directory)


def push_model_version(
    store: ArtifactStore, registry: ModelRegistry, version: str
) -> list[StoredObject]:
    directory = registry.version_dir(version)
    if not directory.is_dir():
        raise StorageError(f"upload {version}: version is not in {registry.root}")
    stored = store.upload_dir(directory, model_prefix(version))
    stored.append(push_registry(store, registry))
    return stored


def push_registry(store: ArtifactStore, registry: ModelRegistry) -> StoredObject:
    return store.upload_file(registry.root / REGISTRY_FILE, registry_key())


def pull_registry(store: ArtifactStore, root: Path) -> ModelRegistry:
    store.download_file(registry_key(), root / REGISTRY_FILE)
    return ModelRegistry(root)


def pull_model_version(store: ArtifactStore, root: Path, version: str) -> Path:
    directory = root / VERSIONS_DIR / version
    store.download_dir(model_prefix(version), directory)
    return directory
