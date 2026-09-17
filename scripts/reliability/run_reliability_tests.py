"""Controlled failures against the real backend.

Runs the handbook's failure scenarios against the packaged backend jar,
the real compose Postgres and Redis containers and real processes, and
records for each one how the failure was detected, how the system
recovered, the job's final result, and the recovery time.

Run from the repository root, with `docker compose up -d` done in
infra/docker/ and the jar built (`./mvnw package -DskipTests` in
backend/):

    .venv/Scripts/python scripts/reliability/run_reliability_tests.py [label]

Writes ml/artifacts/reliability_tests/<label>.json and prints a summary.
Scenarios stop and start the ai-earth-redis and ai-earth-postgres
containers; each one leaves them running again.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / "backend" / "target" / "backend-0.0.1-SNAPSHOT.jar"
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
STUB = ROOT / "scripts" / "reliability" / "stub_forecast.py"
REAL_ANALYSIS_CLI = ROOT / "scripts" / "query" / "run_analysis_cli.py"
REAL_FORECAST_CLI = ROOT / "scripts" / "query" / "run_forecast_cli.py"
OUT_DIR = ROOT / "ml" / "artifacts" / "reliability_tests"
LOG_DIR = OUT_DIR / "logs"

PORT = 8090
MANAGEMENT_PORT = 8091
PYTHON_TIMEOUT_SECONDS = 20
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


@dataclass
class ScenarioResult:
    scenario: str
    injected: str
    expected: str
    detection: list[str] = field(default_factory=list)
    recovery: str = ""
    final_status: str | None = None
    final_error: str | None = None
    recovery_seconds: float | None = None
    passed: bool = False
    observations: dict[str, Any] = field(default_factory=dict)


# --- infrastructure -------------------------------------------------------


def docker(*args: str) -> None:
    subprocess.run(["docker", *args], check=True, capture_output=True)


def http(method: str, path: str, body: Any = None, headers: dict[str, str] | None = None,
         port: int = PORT, timeout: float = 30) -> tuple[int, dict[str, Any] | str]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://localhost:{port}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, text = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read().decode()
    except OSError as error:
        return 0, f"{type(error).__name__}: {error}"
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


class Backend:
    """One backend jar process, started with scenario-specific settings."""

    def __init__(self, name: str, env: dict[str, str]):
        self.name = name
        self.env = env
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> float:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Stays open for the life of the process, which writes to it.
        log = open(LOG_DIR / f"{self.name}-{int(time.time())}.log", "wb")  # noqa: SIM115
        env = {**os.environ, **self.env}
        started = time.monotonic()
        self.process = subprocess.Popen(
            ["java", "-jar", str(JAR)], cwd=ROOT / "backend", env=env, stdout=log, stderr=log
        )
        deadline = started + 240
        while time.monotonic() < deadline:
            status, _ = http("GET", "/actuator/health", port=MANAGEMENT_PORT, timeout=3)
            if status in (200, 503):
                return time.monotonic() - started
            if self.process.poll() is not None:
                raise RuntimeError(f"backend {self.name} exited during startup; see {log.name}")
            time.sleep(1)
        raise RuntimeError(f"backend {self.name} did not start within 240 s")

    def warm_up(self) -> None:
        """One job end to end, so scenarios measure a serving system, not
        a cold JVM's first requests (JPA, Hikari, class loading)."""
        _, body = submit("warmup")
        if isinstance(body, dict) and "forecast_id" in body:
            wait_for(body["forecast_id"], TERMINAL, 60)

    def crash(self) -> None:
        """A hard kill of the whole process tree (the JVM and its Python
        child), as when a pod or node dies: no shutdown hooks run."""
        assert self.process is not None
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], capture_output=True, check=False)
        else:
            subprocess.run(["pkill", "-KILL", "-P", str(self.process.pid)], capture_output=True, check=False)
            self.process.kill()
        self.process.wait(timeout=30)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.crash()


def base_env(queue_key: str) -> dict[str, str]:
    return {
        "SERVER_PORT": str(PORT),
        "MANAGEMENT_PORT": str(MANAGEMENT_PORT),
        "FORECAST_QUEUE_KEY": queue_key,
        "FORECAST_QUEUE_POLL_TIMEOUT_SECONDS": "1",
        "FORECAST_PYTHON_EXECUTABLE": str(PYTHON),
        "FORECAST_PYTHON_SCRIPT": str(STUB),
        "FORECAST_PYTHON_WORKDIR": str(ROOT),
        "FORECAST_PYTHON_TIMEOUT_SECONDS": str(PYTHON_TIMEOUT_SECONDS),
        "FORECAST_WORKER_MAX_ATTEMPTS": "3",
        "FORECAST_RECOVERY_INTERVAL_SECONDS": "5",
        "FORECAST_RECOVERY_RUNNING_GRACE_SECONDS": "10",
        "FORECAST_RECOVERY_QUEUED_AFTER_SECONDS": "10",
        "RATE_LIMIT_FORECASTS_PER_MINUTE": "1000",
        "RATE_LIMIT_ANALYSES_PER_MINUTE": "1000",
        "RATE_LIMIT_KEY_PREFIX": f"ratelimit-reliability-{uuid.uuid4()}:",
    }


# --- forecast helpers -----------------------------------------------------


def forecast_body(behaviour: str) -> dict[str, Any]:
    return {"region": {"kind": "named", "value": behaviour}, "cutoff": "2024-08-15T10:00:00Z"}


def submit(behaviour: str, idempotency_key: str | None = None) -> tuple[int, Any]:
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    return http("POST", "/forecasts", forecast_body(behaviour), headers)


def status_of(forecast_id: str) -> str | None:
    code, body = http("GET", f"/forecasts/{forecast_id}", timeout=5)
    return body.get("status") if code == 200 and isinstance(body, dict) else None


def wait_for(forecast_id: str, statuses: set[str], timeout: float) -> tuple[str | None, float]:
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        last = status_of(forecast_id) or last
        if last in statuses:
            return last, time.monotonic() - started
        time.sleep(0.5)
    return last, time.monotonic() - started


def result_error(forecast_id: str) -> str | None:
    code, body = http("GET", f"/forecasts/{forecast_id}/result")
    return body.get("error") if code == 422 and isinstance(body, dict) else None


def db_scalar(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "ai-earth-postgres", "psql", "-U", "ai_earth", "-d", "ai_earth", "-tAc", sql],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def readyz() -> int:
    return http("GET", "/readyz", timeout=10)[0]


# --- scenarios ------------------------------------------------------------


def duplicate_request(backend: Backend) -> ScenarioResult:
    result = ScenarioResult(
        "duplicate request",
        "10 concurrent POST /forecasts carrying one Idempotency-Key",
        "one row, one job, every response names the same forecast",
    )
    key = f"reliability-{uuid.uuid4()}"
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: submit("sleep-2", key), range(10)))
    batch_seconds = round(time.monotonic() - started, 1)
    codes = sorted(code for code, _ in responses)
    ids = {body.get("forecast_id") for _, body in responses if isinstance(body, dict)}
    rows = int(db_scalar(f"select count(*) from forecasts where idempotency_key = '{key}'"))
    result.observations = {"status_codes": codes, "distinct_forecast_ids": len(ids), "rows": rows,
                           "batch_seconds": batch_seconds}
    result.detection = ["the unique index on idempotency_key; the losing inserts re-read the winner"]
    forecast_id = next(iter(ids))
    final, seconds = wait_for(forecast_id, TERMINAL, 180)
    result.final_status, result.recovery_seconds = final, round(seconds, 1)
    result.recovery = "not needed: duplicates never became jobs"
    result.passed = len(ids) == 1 and rows == 1 and final == "SUCCEEDED" and all(c in (200, 201) for c in codes)
    return result


def job_timeout(backend: Backend) -> list[ScenarioResult]:
    once = ScenarioResult(
        "job timeout (recovers)",
        f"first attempt hangs past forecast.python.timeout-seconds={PYTHON_TIMEOUT_SECONDS}",
        "attempt 1 killed and retried; attempt 2 succeeds",
    )
    code, body = submit(f"slow-once-{uuid.uuid4().hex[:8]}")
    forecast_id = body["forecast_id"]
    retrying, first = wait_for(forecast_id, {"RETRYING"} | TERMINAL, PYTHON_TIMEOUT_SECONDS + 30)
    final, total = wait_for(forecast_id, TERMINAL, 90)
    once.detection = [f"Process.waitFor timed out at {PYTHON_TIMEOUT_SECONDS} s -> PYTHON_TIMEOUT (transient)"]
    once.recovery = "automatic: process killed, job re-enqueued as RETRYING"
    once.final_status = final
    once.recovery_seconds = round(total, 1)
    attempts = int(db_scalar(f"select attempts from forecasts where id = '{forecast_id}'"))
    once.observations = {"first_state_after_timeout": retrying, "seconds_to_retrying": round(first, 1),
                         "attempts": attempts}
    once.passed = retrying in ("RETRYING", "SUCCEEDED") and final == "SUCCEEDED" and attempts == 2

    hang = ScenarioResult(
        "job timeout (gives up)",
        f"every attempt hangs past {PYTHON_TIMEOUT_SECONDS} s",
        "3 attempts, each killed, then FAILED -- never retried forever",
    )
    _, body = submit("hang")
    forecast_id = body["forecast_id"]
    final, total = wait_for(forecast_id, TERMINAL, 3 * PYTHON_TIMEOUT_SECONDS + 60)
    hang.detection = once.detection
    hang.recovery = "bounded: forecast.worker.max-attempts=3"
    hang.final_status, hang.final_error = final, result_error(forecast_id)
    hang.recovery_seconds = round(total, 1)
    hang.observations = {"attempts": int(db_scalar(f"select attempts from forecasts where id = '{forecast_id}'"))}
    hang.passed = final == "FAILED" and hang.observations["attempts"] == 3
    return [once, hang]


def worker_crash(backend: Backend) -> ScenarioResult:
    result = ScenarioResult(
        "worker crash",
        "the backend process tree is killed while a job is RUNNING, then restarted",
        "the restarted backend finds the orphaned job and completes it",
    )
    _, body = submit("sleep-15")
    forecast_id = body["forecast_id"]
    running, _ = wait_for(forecast_id, {"RUNNING"}, 30)
    backend.crash()
    result.observations["state_at_crash"] = running
    startup = backend.start()
    restarted = time.monotonic()
    final, _ = wait_for(forecast_id, TERMINAL, 180)
    result.recovery_seconds = round(time.monotonic() - restarted + startup, 1)
    result.observations["startup_seconds"] = round(startup, 1)
    result.observations["attempts"] = int(db_scalar(f"select attempts from forecasts where id = '{forecast_id}'"))
    result.final_status = final
    result.final_error = result_error(forecast_id)
    result.passed = final == "SUCCEEDED"
    return result


def redis_unavailable(backend: Backend) -> ScenarioResult:
    result = ScenarioResult(
        "Redis unavailable",
        "docker stop ai-earth-redis; submit a forecast; restart Redis 20 s later",
        "the submission is kept and runs once Redis is back",
    )
    docker("stop", "ai-earth-redis")
    try:
        code, body = submit("sleep-1")
        result.observations["submit_status"] = code
        result.observations["submit_body"] = body
        result.observations["readyz_while_down"] = readyz()
        time.sleep(20)
    finally:
        docker("start", "ai-earth-redis")
    restored = time.monotonic()
    forecast_id = body.get("forecast_id") if isinstance(body, dict) else None
    result.detection = [f"/readyz -> {result.observations['readyz_while_down']} while down"]
    if forecast_id is None:
        result.final_status = "NOT ACCEPTED"
        result.recovery = "none: the client must resubmit"
        return result
    final, _ = wait_for(forecast_id, TERMINAL, 120)
    result.final_status = final
    result.recovery_seconds = round(time.monotonic() - restored, 1)
    result.passed = final == "SUCCEEDED"
    return result


def database_unavailable(backend: Backend) -> ScenarioResult:
    result = ScenarioResult(
        "database unavailable",
        "docker stop ai-earth-postgres while a job is RUNNING; submit another; restart 25 s later",
        "new submissions refused with a clear retryable error; the running job completes after recovery",
    )
    code, body = submit("sleep-8")
    forecast_id = body["forecast_id"]
    wait_for(forecast_id, {"RUNNING"}, 30)
    docker("stop", "ai-earth-postgres")
    try:
        code, refused = submit("sleep-1")
        result.observations["submit_while_down"] = {"status": code, "body": refused}
        result.observations["readyz_while_down"] = readyz()
        time.sleep(25)  # the running job's Python finishes while the database is down
    finally:
        docker("start", "ai-earth-postgres")
    restored = time.monotonic()
    result.detection = [f"/readyz -> {result.observations['readyz_while_down']} while down",
                        f"POST /forecasts -> {code} while down"]
    final, _ = wait_for(forecast_id, TERMINAL, 150)
    result.final_status = final
    result.final_error = result_error(forecast_id)
    result.recovery_seconds = round(time.monotonic() - restored, 1)
    result.passed = final == "SUCCEEDED" and code == 503
    return result


def malformed_earth_data() -> ScenarioResult:
    result = ScenarioResult(
        "malformed Earth data",
        "the real analysis pipeline runs over FIRMS history files with one corrupt row",
        "FAILED once with the real parse error -- no retry, service stays up",
    )
    fixture = Path(tempfile.mkdtemp(prefix="ai-earth-malformed-"))
    history = fixture / "data" / "raw" / "firms" / "history"
    history.mkdir(parents=True)
    header = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
              "confidence,version,bright_ti5,frp,daynight\n")
    good = "37.5,-120.5,330.1,0.4,0.4,2024-08-02,1030,N,VIIRS,n,2,290.0,5.1,D\n"
    corrupt = "not-a-latitude,-120.5,330.1,0.4,0.4,2024-08-03,1030,N,VIIRS,n,2,290.0,5.1,D\n"
    for offset in range(0, 50, 5):
        start = date(2024, 7, 6) + timedelta(days=offset)
        (history / f"VIIRS_SNPP_SP_{start.isoformat()}_5d.csv").write_text(header + good, encoding="utf-8")
    (history / "VIIRS_SNPP_SP_2024-08-01_5d.csv").write_text(header + good + corrupt, encoding="utf-8")

    env = base_env(f"reliability-malformed-{uuid.uuid4()}") | {
        "ANALYSIS_PYTHON_EXECUTABLE": str(PYTHON),
        "ANALYSIS_PYTHON_SCRIPT": str(REAL_ANALYSIS_CLI),
        "ANALYSIS_PYTHON_WORKDIR": str(fixture),
    }
    backend = Backend("malformed", env)
    try:
        backend.start()
        code, analysis = http("POST", "/analyses", {
            "question": "fires in California", "intent": "count",
            "region": {"kind": "named", "value": "california"},
            "time_range": {"start": "2024-08-01", "end": "2024-08-05"}, "operation": "count",
        }, timeout=60)
        analysis_id = analysis.get("id") if isinstance(analysis, dict) else None
        analysis_error, analysis_status = None, None
        if analysis_id:
            _, summary = http("GET", f"/analyses/{analysis_id}")
            analysis_status = summary.get("status") if isinstance(summary, dict) else None
            _, res = http("GET", f"/results/{analysis_id}")
            analysis_error = res.get("error") if isinstance(res, dict) else None
        code2, ok = http("POST", "/analyses", {
            "question": "fires in California, again", "intent": "count",
            "region": {"kind": "named", "value": "california"},
            "time_range": {"start": "2024-07-06", "end": "2024-07-11"}, "operation": "count",
        }, timeout=60)
        ok_status = None
        if isinstance(ok, dict) and "id" in ok:
            _, ok_summary = http("GET", f"/analyses/{ok['id']}")
            ok_status = ok_summary.get("status") if isinstance(ok_summary, dict) else None
        result.final_status = analysis_status
        result.final_error = analysis_error
        result.recovery_seconds = 0.0  # synchronous; there is no async recovery to time
        result.observations = {
            "malformed_request": {"submit_status": code, "analysis_status": analysis_status, "error": analysis_error},
            "well_formed_request_after": {"submit_status": code2, "analysis_status": ok_status},
            "readyz_after": readyz(),
        }
        result.detection = ["Python raises on the corrupt row -> exit 1 -> PYTHON_FAILED (permanent, 422)"]
        result.recovery = "not retried (analysis is synchronous, one attempt only); other requests unaffected"
        service_up = result.observations["readyz_after"] == 200
        result.passed = (
            code == 201 and analysis_status == "FAILED" and bool(analysis_error)
            and code2 == 201 and ok_status == "SUCCEEDED"
            and service_up
        )
    finally:
        backend.stop()
        shutil.rmtree(fixture, ignore_errors=True)
    return result


# --- driver ---------------------------------------------------------------


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if not JAR.exists():
        sys.exit(f"build the backend first: {JAR} not found")

    results: list[ScenarioResult] = []
    backend = Backend("main", base_env(f"reliability-{uuid.uuid4()}"))
    try:
        backend.start()
        backend.warm_up()
        for scenario in (duplicate_request, job_timeout, redis_unavailable, database_unavailable, worker_crash):
            print(f"-- {scenario.__name__}", flush=True)
            outcome = scenario(backend)
            results.extend(outcome if isinstance(outcome, list) else [outcome])
    finally:
        backend.stop()
        docker("start", "ai-earth-redis")
        docker("start", "ai-earth-postgres")
    print("-- malformed_earth_data", flush=True)
    results.append(malformed_earth_data())

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"label": label, "ran_at": datetime.now(timezone.utc).isoformat(),
              "python_timeout_seconds": PYTHON_TIMEOUT_SECONDS, "scenarios": [asdict(r) for r in results]}
    path = OUT_DIR / f"{label}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    for r in results:
        seconds = "-" if r.recovery_seconds is None else f"{r.recovery_seconds:>6.1f}s"
        print(f"{'PASS' if r.passed else 'FAIL'}  {r.scenario:<26} {r.final_status!s:<12} {seconds}")
    print(f"report: {path}")


if __name__ == "__main__":
    main()
