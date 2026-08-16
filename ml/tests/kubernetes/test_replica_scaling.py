import json

from ai_earth_intelligence_and_forecasting_engine.kubernetes.replica_scaling import (
    replica_scaling_trial_to_dict,
    run_replica_scaling_trial,
    save_replica_scaling_results,
)


def _fake_clock(step_seconds: float = 1.0):
    state = {"t": 0.0}

    def now() -> float:
        return state["t"]

    def sleep(seconds: float) -> None:
        state["t"] += seconds

    return now, sleep


def test_run_replica_scaling_trial_all_jobs_succeed_immediately():
    now, sleep = _fake_clock()
    job_ids = iter(["a", "b", "c"])
    statuses = {"a": "SUCCEEDED", "b": "SUCCEEDED", "c": "SUCCEEDED"}

    result = run_replica_scaling_trial(
        replicas=2,
        job_count=3,
        submit_job=lambda: next(job_ids),
        poll_job_status=lambda job_id: statuses[job_id],
        sleep=sleep,
        now=now,
    )

    assert result.replicas == 2
    assert result.job_count == 3
    assert result.status_counts == {"SUCCEEDED": 3}
    assert len(result.per_job_seconds) == 3


def test_run_replica_scaling_trial_polls_until_terminal_status():
    now, sleep = _fake_clock()
    polls = {"a": iter(["RUNNING", "RUNNING", "FAILED"])}

    result = run_replica_scaling_trial(
        replicas=1,
        job_count=1,
        submit_job=lambda: "a",
        poll_job_status=lambda job_id: next(polls[job_id]),
        poll_interval_seconds=2.0,
        sleep=sleep,
        now=now,
    )

    assert result.status_counts == {"FAILED": 1}
    # two RUNNING polls before the terminal one -> two 2s sleeps elapsed
    assert result.total_wall_seconds == 4.0
    assert result.per_job_seconds == (4.0,)


def test_run_replica_scaling_trial_throughput_is_job_count_over_wall_time():
    now, sleep = _fake_clock()
    statuses = iter(["RUNNING", "SUCCEEDED"])

    result = run_replica_scaling_trial(
        replicas=4,
        job_count=1,
        submit_job=lambda: "only",
        poll_job_status=lambda job_id: next(statuses),
        poll_interval_seconds=5.0,
        sleep=sleep,
        now=now,
    )

    assert result.total_wall_seconds == 5.0
    assert result.throughput_jobs_per_second == 1 / 5.0


def test_failed_jobs_count_as_completed_work_not_errors():
    now, sleep = _fake_clock()
    job_ids = iter(["a", "b"])
    statuses = {"a": "FAILED", "b": "SUCCEEDED"}

    result = run_replica_scaling_trial(
        replicas=1,
        job_count=2,
        submit_job=lambda: next(job_ids),
        poll_job_status=lambda job_id: statuses[job_id],
        sleep=sleep,
        now=now,
    )

    assert result.status_counts == {"FAILED": 1, "SUCCEEDED": 1}
    assert sum(result.status_counts.values()) == result.job_count


def test_replica_scaling_trial_to_dict_is_json_serializable():
    now, sleep = _fake_clock()

    result = run_replica_scaling_trial(
        replicas=1,
        job_count=1,
        submit_job=lambda: "only",
        poll_job_status=lambda job_id: "SUCCEEDED",
        sleep=sleep,
        now=now,
    )

    payload = replica_scaling_trial_to_dict(result)
    json.dumps(payload)

    assert payload["replicas"] == 1
    assert payload["job_count"] == 1


def test_save_replica_scaling_results_roundtrip(tmp_path):
    now, sleep = _fake_clock()

    result = run_replica_scaling_trial(
        replicas=1,
        job_count=1,
        submit_job=lambda: "only",
        poll_job_status=lambda job_id: "SUCCEEDED",
        sleep=sleep,
        now=now,
    )

    output_path = tmp_path / "replica_scaling_benchmark.json"
    saved_path = save_replica_scaling_results([result], output_path)
    saved = json.loads(saved_path.read_text(encoding="utf-8"))

    assert saved["benchmark_version"] == "v1"
    assert len(saved["trials"]) == 1
    assert saved["trials"][0]["replicas"] == 1
