import pytest

from ai_earth_intelligence_and_forecasting_engine.kubernetes.benchmark import (
    FailureRecoveryResult,
    measure_failure_recovery,
    parse_kubectl_top_pods,
)


def test_parse_kubectl_top_pods_real_output_with_header():
    output = (
        "NAME                       CPU(cores)   MEMORY(bytes)   \n"
        "backend-5f875b7d66-44zh6   15m          652Mi           \n"
    )

    usages = parse_kubectl_top_pods(output)

    assert len(usages) == 1
    assert usages[0].pod_name == "backend-5f875b7d66-44zh6"
    assert usages[0].cpu_millicores == 15
    assert usages[0].memory_mebibytes == 652.0


def test_parse_kubectl_top_pods_multiple_pods():
    output = (
        "NAME       CPU(cores)   MEMORY(bytes)\n"
        "backend-a  120m         700Mi\n"
        "backend-b  95m          680Mi\n"
    )

    usages = parse_kubectl_top_pods(output)

    assert [u.pod_name for u in usages] == ["backend-a", "backend-b"]
    assert [u.cpu_millicores for u in usages] == [120, 95]


def test_parse_kubectl_top_pods_converts_gi_and_ki_to_mebibytes():
    output = "NAME   CPU(cores)   MEMORY(bytes)\npod-a  1            1Gi\npod-b  10m          1024Ki\n"  # noqa: E501

    usages = parse_kubectl_top_pods(output)

    assert usages[0].cpu_millicores == 1000
    assert usages[0].memory_mebibytes == 1024.0
    assert usages[1].memory_mebibytes == 1.0


def test_parse_kubectl_top_pods_empty_output_returns_empty_list():
    assert parse_kubectl_top_pods("") == []


def test_parse_kubectl_top_pods_rejects_unrecognized_memory_unit():
    with pytest.raises(ValueError):
        parse_kubectl_top_pods("NAME  CPU(cores)  MEMORY(bytes)\npod-a  1m  5Xi\n")


def _fake_clock():
    state = {"t": 0.0}

    def now() -> float:
        return state["t"]

    def sleep(seconds: float) -> None:
        state["t"] += seconds

    return now, sleep


def test_measure_failure_recovery_times_until_ready():
    now, sleep = _fake_clock()
    readiness = iter([False, False, True])

    result = measure_failure_recovery(
        delete_pod=lambda: None,
        is_ready=lambda: next(readiness),
        poll_interval_seconds=5.0,
        sleep=sleep,
        now=now,
    )

    assert isinstance(result, FailureRecoveryResult)
    assert result.recovery_seconds == 10.0


def test_measure_failure_recovery_immediate_ready_is_zero_seconds():
    now, sleep = _fake_clock()

    result = measure_failure_recovery(
        delete_pod=lambda: None,
        is_ready=lambda: True,
        sleep=sleep,
        now=now,
    )

    assert result.recovery_seconds == 0.0


def test_measure_failure_recovery_raises_on_timeout():
    now, sleep = _fake_clock()

    with pytest.raises(TimeoutError):
        measure_failure_recovery(
            delete_pod=lambda: None,
            is_ready=lambda: False,
            poll_interval_seconds=10.0,
            timeout_seconds=25.0,
            sleep=sleep,
            now=now,
        )


def test_measure_failure_recovery_calls_delete_pod_exactly_once():
    now, sleep = _fake_clock()
    calls = {"count": 0}

    def delete_pod():
        calls["count"] += 1

    measure_failure_recovery(
        delete_pod=delete_pod,
        is_ready=lambda: True,
        sleep=sleep,
        now=now,
    )

    assert calls["count"] == 1
