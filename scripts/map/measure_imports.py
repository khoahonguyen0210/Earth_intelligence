import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

STATEMENTS = {
    "torch": "import torch",
    "earth2studio": "import torch; import earth2studio",
    "earth2studio_data": "import torch; import earth2studio.data",
    "earth2studio_models": "import torch; import earth2studio.models.px",
    "daily_run": (
        "import torch; import earth2studio.data; import earth2studio.models.px"
    ),
}


def largest(values: dict[str, float], count: int) -> dict[str, float]:
    ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)
    return {name: round(value, 2) for name, value in ranked[:count]}


def measure(statement: str) -> dict:
    started = time.perf_counter()
    finished = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", statement],
        capture_output=True,
        text=True,
        check=True,
    )
    seconds = time.perf_counter() - started
    by_package: dict[str, float] = defaultdict(float)
    by_module: dict[str, float] = {}
    for line in finished.stderr.splitlines():
        if not line.startswith("import time:") or "self [us]" in line:
            continue
        own, _, name = line[len("import time:") :].split("|")
        module = name.strip()
        by_package[module.split(".")[0]] += int(own) / 1e6
        by_module[module] = int(own) / 1e6
    return {
        "seconds": round(seconds, 2),
        "packages": largest(by_package, 25),
        "modules": largest(by_module, 25),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("import_times.json"))
    parser.add_argument("--repeats", type=int, default=2)
    arguments = parser.parse_args()

    results = {
        name: [measure(statement) for _ in range(arguments.repeats)]
        for name, statement in STATEMENTS.items()
    }
    arguments.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    for name, runs in results.items():
        print(name, [run["seconds"] for run in runs])
        print("  ", list(runs[-1]["packages"].items())[:10])
        print("  ", list(runs[-1]["modules"].items())[:10])


if __name__ == "__main__":
    main()
