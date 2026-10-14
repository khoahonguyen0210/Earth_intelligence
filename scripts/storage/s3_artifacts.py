import argparse
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from ai_earth_intelligence_and_forecasting_engine.models.retraining import (
    ModelRegistry,
    deploy,
)
from ai_earth_intelligence_and_forecasting_engine.storage.artifacts import (
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

DATASET_DIR = Path("data/processed")
SERVED_DIR = Path("ml/artifacts/production_model_v1")
REGISTRY_DIR = Path("ml/artifacts/model_registry")


def show(stored) -> None:
    for item in stored:
        print(f"  {item.key}  {item.size:,} bytes  sha256 {item.sha256[:12]}")


def push_model(store: ArtifactStore, version: str | None) -> None:
    registry = ModelRegistry(REGISTRY_DIR)
    version = version or registry.current
    if version is None:
        raise StorageError(
            "upload model: the local registry has no current version; run "
            "scripts/models/retrain.py --register-current first"
        )
    stored = push_model_version(store, registry, version)
    print(f"uploaded model {version}:")
    show(stored)


def pull_model(store: ArtifactStore, version: str | None, serve: bool) -> None:
    if version is None:
        with tempfile.TemporaryDirectory() as scratch:
            version = pull_registry(store, Path(scratch)).current
        if version is None:
            raise StorageError(
                "download model: the remote registry has no current version"
            )
    directory = pull_model_version(store, REGISTRY_DIR, version)
    print(f"downloaded model {version} -> {directory}")
    if serve:
        deploy(directory, SERVED_DIR)
        print(f"serving {version} from {SERVED_DIR}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Move datasets and models to and from S3."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="confirm the bucket is reachable")
    commands.add_parser("push-datasets", help=f"upload datasets from {DATASET_DIR}")
    commands.add_parser("pull-datasets", help=f"download datasets into {DATASET_DIR}")
    push = commands.add_parser("push-model", help="upload a registry version")
    push.add_argument("--version", help="defaults to the local current version")
    pull = commands.add_parser("pull-model", help="download a registry version")
    pull.add_argument("--version", help="defaults to the remote current version")
    pull.add_argument(
        "--serve", action="store_true", help=f"also deploy to {SERVED_DIR}"
    )
    listing = commands.add_parser("list", help="list stored objects")
    listing.add_argument("--prefix", default="ml/")
    upload = commands.add_parser("upload", help="upload one file")
    upload.add_argument("path", type=Path)
    upload.add_argument("key")
    download = commands.add_parser("download", help="download one file")
    download.add_argument("key")
    download.add_argument("path", type=Path)
    args = parser.parse_args()

    store = ArtifactStore.from_env()
    if store is None:
        print("ARTIFACT_BUCKET is not set; see docs/s3-artifacts.md", file=sys.stderr)
        return 2

    try:
        store.check_bucket()
        if args.command == "check":
            print(f"s3://{store.bucket} is reachable")
        elif args.command == "push-datasets":
            stored = push_datasets(store, DATASET_DIR)
            print(f"uploaded {len(stored)} dataset files:")
            show(stored)
        elif args.command == "pull-datasets":
            paths = pull_datasets(store, DATASET_DIR)
            print(f"downloaded {len(paths)} dataset files into {DATASET_DIR}")
        elif args.command == "push-model":
            push_model(store, args.version)
        elif args.command == "pull-model":
            pull_model(store, args.version, args.serve)
        elif args.command == "list":
            for key in store.list_keys(args.prefix):
                print(key)
        elif args.command == "upload":
            show([store.upload_file(args.path, args.key)])
        elif args.command == "download":
            stored = store.download_file(args.key, args.path)
            print(f"downloaded {stored.key} -> {args.path} ({stored.size:,} bytes)")
    except StorageError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
