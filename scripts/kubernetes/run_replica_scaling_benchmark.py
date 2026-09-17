import os
import subprocess
import time
from pathlib import Path

import requests

from ai_earth_intelligence_and_forecasting_engine.kubernetes.replica_scaling import (
    replica_scaling_trial_to_dict,
    run_replica_scaling_trial,
    save_replica_scaling_results,
)

BACKEND_BASE_URL = os.environ.get("FORECAST_API_BASE_URL", "http://localhost:8080")
DEPLOYMENT = "deployment/backend"
REPLICA_COUNTS = (1, 2, 4, 8)
JOBS_PER_TRIAL = 8

FORECAST_REQUEST = {
    "region": {"kind": "named", "value": "california"},
    "cutoff": "2024-08-15T10:00:00Z",
}


def kubectl(*args: str, retries: int = 3) -> str:
    for attempt in range(retries):
        result = subprocess.run(["kubectl", *args], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        if attempt == retries - 1:
            raise RuntimeError(
                f"kubectl {' '.join(args)} failed: {result.stderr.strip()}"
            )
        time.sleep(2)
    raise AssertionError("unreachable")


def scale_backend_and_wait(replicas: int, timeout_seconds: float = 180.0) -> None:
    kubectl("scale", DEPLOYMENT, f"--replicas={replicas}")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        out = kubectl("get", "pods", "-l", "app=backend", "--no-headers")
        lines = [line for line in out.splitlines() if line.strip()]
        ready = sum(1 for line in lines if line.split()[1] == "1/1")
        if ready == replicas and len(lines) == replicas:
            return
        time.sleep(3)
    raise TimeoutError(f"backend did not reach {replicas} ready replica(s) in time")


def submit_job() -> str:
    response = requests.post(
        f"{BACKEND_BASE_URL}/forecasts", json=FORECAST_REQUEST, timeout=30
    )
    response.raise_for_status()
    return response.json()["forecast_id"]


def poll_job_status(forecast_id: str) -> str:
    response = requests.get(
        f"{BACKEND_BASE_URL}/forecasts/{forecast_id}", timeout=30
    )
    response.raise_for_status()
    return response.json()["status"]


def main() -> None:
    trials = []
    for replicas in REPLICA_COUNTS:
        print(f"=== scaling backend to {replicas} replica(s) ===")
        scale_backend_and_wait(replicas)

        trial = run_replica_scaling_trial(
            replicas=replicas,
            job_count=JOBS_PER_TRIAL,
            submit_job=submit_job,
            poll_job_status=poll_job_status,
        )
        print(replica_scaling_trial_to_dict(trial))
        trials.append(trial)

    # Leave the cluster at a normal single-instance baseline afterward.
    scale_backend_and_wait(1)

    output_path = Path("data/processed/benchmark/replica_scaling_benchmark.json")
    save_replica_scaling_results(trials, output_path)
    print(f"Saved benchmark result to: {output_path}")


if __name__ == "__main__":
    main()
