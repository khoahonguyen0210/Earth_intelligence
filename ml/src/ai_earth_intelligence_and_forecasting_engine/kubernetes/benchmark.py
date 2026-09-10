from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable

MEMORY_UNIT_TO_MEBIBYTES = {"ki": 1 / 1024, "mi": 1, "gi": 1024}


@dataclass(frozen=True)
class PodResourceUsage:
    pod_name: str
    cpu_millicores: int
    memory_mebibytes: float


def parse_kubectl_top_pods(output: str) -> list[PodResourceUsage]:
    """Parses real `kubectl top pods` text output (a header line, then one
    line per pod: NAME CPU(cores) MEMORY(bytes)). Real `kubectl` reports
    CPU in millicores ("15m") and memory with a Ki/Mi/Gi suffix ("652Mi")
    -- this normalizes both to a single unit (millicores, mebibytes) so
    an idle pod can be compared against a loaded one without unit
    conversion scattered through the caller.
    """
    lines = [line for line in output.strip().splitlines() if line.strip()]
    if not lines:
        return []

    data_lines = lines[1:] if lines[0].upper().startswith("NAME") else lines

    usages = []
    for line in data_lines:
        name, cpu_raw, memory_raw = line.split()[:3]
        usages.append(
            PodResourceUsage(
                pod_name=name,
                cpu_millicores=_parse_cpu_millicores(cpu_raw),
                memory_mebibytes=_parse_memory_mebibytes(memory_raw),
            )
        )
    return usages


def _parse_cpu_millicores(raw: str) -> int:
    if raw.endswith("m"):
        return int(raw[:-1])
    return int(float(raw) * 1000)


def _parse_memory_mebibytes(raw: str) -> float:
    match = re.match(r"^(\d+(?:\.\d+)?)([A-Za-z]+)$", raw)
    if not match:
        raise ValueError(f"unrecognized memory value: {raw!r}")
    value, unit = float(match.group(1)), match.group(2).lower()
    if unit not in MEMORY_UNIT_TO_MEBIBYTES:
        raise ValueError(f"unsupported memory unit in {raw!r}")
    return value * MEMORY_UNIT_TO_MEBIBYTES[unit]


@dataclass(frozen=True)
class FailureRecoveryResult:
    recovery_seconds: float


def measure_failure_recovery(
    delete_pod: Callable[[], None],
    is_ready: Callable[[], bool],
    poll_interval_seconds: float = 1.0,
    timeout_seconds: float = 180.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> FailureRecoveryResult:
    """Times real recovery from a real failure: `delete_pod` kills the
    running pod (a real `kubectl delete pod`), then this polls `is_ready`
    until the Deployment controller's replacement pod reports ready
    again.
    `sleep`/`now` are injected for unit testing against a fake clock, the
    same pattern `run_replica_scaling_trial` already uses.
    """
    start = now()
    delete_pod()

    deadline = start + timeout_seconds
    while now() < deadline:
        if is_ready():
            return FailureRecoveryResult(recovery_seconds=now() - start)
        sleep(poll_interval_seconds)

    raise TimeoutError(
        f"pod did not become ready again within {timeout_seconds}s of deletion"
    )
