import argparse
import json
from pathlib import Path

KERNEL_DIR = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    code = (KERNEL_DIR / "daily_kernel.py").read_text(encoding="utf-8")
    for name, value in (
        ("__REPOSITORY__", arguments.repository),
        ("__COMMIT__", arguments.commit),
        ("__CUTOFF__", arguments.cutoff),
    ):
        code = code.replace(name, value)

    arguments.output.mkdir(parents=True, exist_ok=True)
    (arguments.output / "daily_kernel.py").write_text(code, encoding="utf-8")
    metadata = {
        "id": arguments.kernel_id,
        "title": arguments.kernel_id.split("/")[-1].replace("-", " "),
        "code_file": "daily_kernel.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
    }
    (arguments.output / "kernel-metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
