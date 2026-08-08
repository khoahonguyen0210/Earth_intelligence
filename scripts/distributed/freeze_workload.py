import json
from dataclasses import asdict
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.distributed.workload import (
    freeze_workload,
)

OUTPUT_PATH = Path("ml/artifacts/distributed_workload_v1/workload.json")


def main() -> None:
    workload = freeze_workload()
    record = asdict(workload) | {"workload_size": workload.workload_size}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"Froze a {workload.workload_size}-tile distributed workload:")
    print(f"  grid_version:    {workload.grid_version}")
    print(f"  dataset_version: {workload.dataset_version}")
    print(f"  feature_version: {workload.feature_version}")
    print(f"  model_version:   {workload.model_version}")
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
