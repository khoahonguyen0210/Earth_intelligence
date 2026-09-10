import json
import os
import subprocess
import time
from pathlib import Path

import requests

from ai_earth_intelligence_and_forecasting_engine.kubernetes.benchmark import (
    measure_failure_recovery,
    parse_kubectl_top_pods,
)
from ai_earth_intelligence_and_forecasting_engine.kubernetes.replica_scaling import (
    ReplicaScalingTrialResult,
    compute_speedup_efficiency,
    replica_scaling_point_to_dict,
)

BACKEND_BASE_URL = os.environ.get("FORECAST_API_BASE_URL", "http://localhost:8080")
FORECAST_REQUEST = {
    "region": {"kind": "named", "value": "california"},
    "cutoff": "2024-08-15T10:00:00Z",
}

# Runtime/throughput already measured for real
# (docs/worker-replica-scaling.md) on this exact cluster -- re-running
# the same 1/2/4/8 sweep here would just reproduce (with normal run-to-
# run noise) an already-locked result. Speedup/efficiency are computed
# fresh from those real numbers below; resource usage and failure
# recovery are this script's own new real measurements.
LOCKED_TASK_11_3_TRIALS = [
    ReplicaScalingTrialResult(1, 8, 64.2856718999974, 0.12444452649487395, (), {"FAILED": 8}),
    ReplicaScalingTrialResult(2, 8, 51.32596069999272, 0.155866541822005, (), {"FAILED": 8}),
    ReplicaScalingTrialResult(4, 8, 56.76142000002437, 0.1409408009876526, (), {"FAILED": 8}),
    ReplicaScalingTrialResult(8, 8, 111.94309380001505, 0.07146488209707605, (), {"FAILED": 8}),
]


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


def wait_for_ready_replicas(replicas: int, timeout_seconds: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        out = kubectl("get", "pods", "-l", "app=backend", "--no-headers")
        lines = [line for line in out.splitlines() if line.strip()]
        ready = sum(1 for line in lines if line.split()[1] == "1/1")
        if ready == replicas and len(lines) == replicas:
            return
        time.sleep(3)
    raise TimeoutError(f"backend did not reach {replicas} ready replica(s) in time")


def wait_for_pod_count(count: int, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        out = kubectl("get", "pods", "-l", "app=backend", "--no-headers")
        lines = [line for line in out.splitlines() if line.strip()]
        if len(lines) >= count:
            return
        time.sleep(2)
    raise TimeoutError(f"backend did not scale to {count} pod(s) in time")


def measure_resource_usage() -> dict:
    """Idle usage at the steady-state 1 replica, then real usage while
    KEDA's own autoscaler reacts to a genuine queue backlog
    and scales to 2 -- not a synthetic bypass of the autoscaler.

    8 jobs, not fewer: with only a handful
    of jobs, one already-running replica can drain the backlog before
    the second replica's ~45s JVM boot even finishes, so the
    scale-up arrives, briefly exists, and reverts again inside one
    window this script could easily poll straight through -- observed
    directly when this script's first draft used 4 jobs. Capturing usage
    the moment the second pod is scheduled (not waiting for it to be
    fully Ready) is what a real "scaling up under load" resource-usage
    sample actually looks like.
    """
    wait_for_ready_replicas(1)
    idle = parse_kubectl_top_pods(kubectl("top", "pods", "-l", "app=backend"))

    for _ in range(8):
        response = requests.post(
            f"{BACKEND_BASE_URL}/forecasts", json=FORECAST_REQUEST, timeout=30
        )
        response.raise_for_status()

    wait_for_pod_count(2, timeout_seconds=60.0)
    time.sleep(15)  # let metrics-server take at least one sample of the new pod
    under_load = parse_kubectl_top_pods(kubectl("top", "pods", "-l", "app=backend"))

    wait_for_ready_replicas(1, timeout_seconds=180.0)  # let it drain and scale back down

    return {
        "idle_1_replica": [vars(u) for u in idle],
        "under_load_2_replicas": [vars(u) for u in under_load],
    }


def measure_recovery() -> dict:
    wait_for_ready_replicas(1)
    pod_name = kubectl(
        "get", "pods", "-l", "app=backend", "-o", "jsonpath={.items[0].metadata.name}"
    )

    def delete_pod() -> None:
        kubectl("delete", "pod", pod_name)

    def is_ready() -> bool:
        out = kubectl("get", "pods", "-l", "app=backend", "--no-headers")
        lines = [line for line in out.splitlines() if line.strip()]
        return len(lines) == 1 and lines[0].split()[1] == "1/1"

    result = measure_failure_recovery(delete_pod, is_ready, poll_interval_seconds=2.0)
    return {"recovery_seconds": result.recovery_seconds}


def main() -> None:
    scaling_points = [
        replica_scaling_point_to_dict(p)
        for p in compute_speedup_efficiency(LOCKED_TASK_11_3_TRIALS)
    ]
    print("=== runtime / throughput / speedup / efficiency (Task 11.3 data) ===")
    for point in scaling_points:
        print(point)

    print("=== resource usage ===")
    resource_usage = measure_resource_usage()
    print(resource_usage)

    print("=== failure recovery ===")
    recovery = measure_recovery()
    print(recovery)

    output_path = Path("data/processed/benchmark/kubernetes_benchmark.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "scaling": scaling_points,
                "resource_usage": resource_usage,
                "failure_recovery": recovery,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved benchmark result to: {output_path}")


if __name__ == "__main__":
    main()
