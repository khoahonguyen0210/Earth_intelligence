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
