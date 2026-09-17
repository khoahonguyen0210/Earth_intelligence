# Reliability Tests — LOCKED

This document freezes the reliability testing. It is not a
brainstorming document.

The handbook lists seven controlled failures. Six are exercised end to
end against the real, running system by
`scripts/reliability/run_reliability_tests.py`; the seventh (partial
workflow failure) has no HTTP entry point yet
(`docs/workflow-execution.md` -- `WorkflowExecutor` is not wired to a
route) and is instead a `@SpringBootTest` against the real
`WorkflowExecutor`/`WorkflowStore`, `WorkflowPartialFailureIntegrationTest`.

## What the harness actually does

`scripts/reliability/run_reliability_tests.py` starts the packaged
backend jar as a real OS process, against the real `docker compose`
Postgres and Redis, with a stub Python pipeline
(`scripts/reliability/stub_forecast.py`) whose behavior is chosen by the
request's own region name (`sleep-<n>`, `slow-once-<nonce>`, `hang`, or
anything else = succeed immediately). It then, per scenario: submits real
HTTP requests, kills the real backend process (`taskkill /T` on Windows,
`SIGKILL` on the process group elsewhere -- a hard kill, no shutdown
hooks, standing in for a crashed pod or node), stops and restarts the
real `ai-earth-redis`/`ai-earth-postgres` containers, and polls the real
`/forecasts/{id}` endpoint until a terminal state or a timeout. Nothing
here is mocked. Malformed Earth data runs the real
`run_analysis_cli.py`/`run_forecast_cli.py` against a fixture FIRMS
history directory containing one corrupt CSV row.

Run it (from the repository root, `docker compose up -d` done, backend
jar built with `./mvnw package -DskipTests`):

```bash
.venv/Scripts/python scripts/reliability/run_reliability_tests.py <label>
```

It writes `ml/artifacts/reliability_tests/<label>.json` (one record per
scenario: how it was detected, how it recovered, the final result, and
the recovery time) and prints a summary table.

## Before: three real gaps, found by running the failures for real

A first run, before any fix, against the code as it stood before this work:

```text
PASS  duplicate request           SUCCEEDED       2.9s
PASS  job timeout (recovers)      SUCCEEDED       1.2s
PASS  job timeout (gives up)      FAILED         67.0s
FAIL  Redis unavailable           NOT ACCEPTED    -
FAIL  database unavailable        RUNNING       150.3s
FAIL  worker crash                RUNNING       285.3s
FAIL  malformed Earth data        FAILED         61.4s
```

Three real, load-bearing gaps this task exists to close:

- **Redis unavailable → the job is silently dropped.** `POST /forecasts`
  saved the row, then called `queue.enqueue` unguarded; a
  `DataAccessException` there propagated out of the controller as a bare
  500, and the client got no forecast id to poll -- the request simply
  vanished from the client's point of view, even though a `PENDING` row
  existed nobody would ever run.
- **Database unavailable mid-job → the job is stuck `RUNNING` forever.**
  `ForecastWorker.attempt` wrote `RUNNING` before running the job and the
  outcome after; if the outcome write failed (or the whole worker died
  in between), nothing ever moved the row again. Waited 150s; still
  `RUNNING`.
- **Worker crash mid-job → the job is stuck `RUNNING` forever,** for the
  same reason -- and this is exactly the gap `docs/forecast-async-jobs.md`
  named up front: "a worker that dies between popping an id
  and finishing the job loses that job today -- there is no redelivery or
  visibility timeout." Waited 285s; still `RUNNING`.

The two other "failures" above were the harness being too strict, not
real bugs, fixed in the harness itself, not the product:

- "job timeout (gives up)" and "malformed Earth data" failed only an
  exact-wording assertion in the script, not the underlying behavior
  (both already reached `FAILED` for the right reason). Loosened to
  check the substance (attempts exhausted; the error names the bad
  file) rather than a literal string.

## The fix: ForecastRecovery, plus an atomic claim

Two changes closed all three gaps, without changing the queue's message
format (a bare id) or `ForecastQueue`'s interface beyond one new method:

**1. `Forecast.updated_at` (Flyway `V5`) and an atomic claim.** Every
save stamps `updated_at`. `ForecastJpaRepository.claim` is one
conditional `UPDATE ... SET status = 'RUNNING' ... WHERE status IN
('PENDING', 'RETRYING')`: it succeeds only if the row is still waiting,
so of two workers holding the same id (a duplicate queue entry, or a
job re-enqueued while a worker still has it) exactly one runs it. The
worker calls `store.claim` before running anything, instead of writing
`RUNNING` unconditionally.

**2. `ForecastRecovery`, a `@Scheduled` sweep on every replica.** Postgres
is the source of truth; the Redis list is only a hint of what to run
next. Two cases, both judged by how long a row has gone without
changing:

```text
abandoned attempt   RUNNING longer than forecast.python.timeout-seconds
                    + a grace period: the worker died, or its final
                    write failed. Counts as a failed attempt
                    (WORKER_LOST, transient) -- RETRYING and
                    re-enqueued while attempts remain, else FAILED, the
                    same budget as any other retry.
orphaned job        PENDING/RETRYING longer than the threshold AND not
                    in the Redis list: its queue entry was never
                    written (Redis was down at submit time) or was
                    popped by a worker that then could not run it.
                    Re-enqueued. A job merely waiting behind a normal
                    backlog is still in the list and is left alone.
```

Every change recovery makes is itself a conditional `UPDATE` (only
succeeds if the row is still in the state and age the sweep saw), so two
replicas' sweeps -- or a sweep racing a worker that just picked the job
up -- never both act on one job. `ForecastRecoveryIntegrationTest` proves
this directly: two sequential sweeps over one abandoned job recover it
exactly once, not twice.

**3. The worker and the controller stop treating a dependency outage as
a bug.** `ForecastWorker.pollOnce`/`process` catch `DataAccessException`
around the dequeue and around the whole attempt, log one `WARN` per
outage (not one per 100 ms poll) and back off
(`forecast.worker.error-backoff-ms`) instead of spinning. `POST
/forecasts` catches the same exception around `queue.enqueue` alone: the
row is still saved and `201` still returned with a real forecast id --
recovery enqueues it once Redis is back. A genuine dependency failure
(`DataAccessResourceFailureException`/`CannotCreateTransactionException`/
`TransientDataAccessException`) reaching the API returns `503` with
`Retry-After`, not a bare `500` (`ApiErrorHandler.dependencyUnavailable`).
Postgres's own connection timeout is cut from Hikari's 30 s default to 5 s
(`spring.datasource.hikari.connection-timeout`), so a request fails fast
enough to be worth a `503` at all.

## After: the same six scenarios, run again

```text
PASS  duplicate request           SUCCEEDED       2.3s
PASS  job timeout (recovers)      SUCCEEDED       0.0s
PASS  job timeout (gives up)      FAILED         62.1s
PASS  Redis unavailable           SUCCEEDED      18.9s
PASS  database unavailable        SUCCEEDED      15.9s
PASS  worker crash                SUCCEEDED      89.9s
PASS  malformed Earth data        FAILED          0.0s
```

(`ml/artifacts/reliability_tests/final.json` is the run behind this
table; earlier runs in that same directory, `before`/`after`/`after2`,
are kept as the record of what each fix actually changed.)

All six now recover, or fail cleanly and by design, with the service
staying up throughout. Two more things this run found, beyond the three
gaps `ForecastRecovery` closes:

**Lettuce has no command timeout by default.** With Redis genuinely
unreachable (`docker stop`), `queue.enqueue`'s `LPUSH` blocked for
upwards of a minute before failing -- long past the point of `POST
/forecasts` being a useful "accepted, try again" response. Fixed with
`spring.data.redis.timeout=8000ms`. That value has to stay above
`forecast.queue.poll-timeout-seconds` (the worker's own blocking `RPOP`
is *supposed* to wait that long on an empty queue, default 5 s): a
shorter client timeout would misfire on every ordinary idle poll, not
just a real outage.

**A shared, long-lived dev database changes what "the same test" measures.**
The first "duplicate request" rerun took over 60 s instead of ~3 s, with
no product change at all. `ForecastRecovery` was doing exactly its job:
sweeping in every job left orphaned by *earlier* sessions' manual runs
and reliability-test runs (dozens of them, accumulated over hours in
this one Postgres), which real production traffic would never have all
lodged at once. Confirmed directly by log-walking the run and finding
`job_requeued` events for pre-existing ids competing, FIFO, with the
scenario's own new job for the same freshly-reused queue key. Not a
product bug -- widened the scenario's own wait budget to 180 s (a real
backlog is still a real backlog, and the job did still finish) and
documented it here rather than hiding it.

The malformed-data forecast leg was dropped rather than fixed: it needs
a full ERA5/geography/model fixture that a FIRMS-only directory can't
stand in for, and hit its own `forecast.python.timeout-seconds` (missing
inputs, not the corrupt row) instead of the intended failure. The
analysis leg alone -- run against the real pipeline, over the real
corrupt row -- already proves the property this scenario exists to
check, plus a well-formed follow-up request on the same running service
to prove the corrupt row didn't wedge anything else.

## Partial workflow failure

`WorkflowPartialFailureIntegrationTest` runs the handbook's forecast DAG
plus an independent branch through the real `WorkflowExecutor` against
real Postgres:

```text
get_data -> validate -> build_features (transient once) -> run_forecast (permanent)
                     \                                        -> get_result_evidence
                      -> calculate_statistics                  -> generate_map
```

`build_features` fails transiently once and recovers on retry (already
proven correct by the workflow executor's own tests; re-asserted here
in the fuller DAG). `run_forecast` fails permanently: only that node is marked
`FAILED`, `get_result_evidence` and `generate_map` are `CANCELLED`
without ever being dispatched, and the independent
`calculate_statistics` branch and every upstream node still reach
`SUCCEEDED`. The workflow is saved and reloaded from Postgres, so the
persisted state matches, not just the in-memory one. Retries are
in-line (no queue, no wait between attempts), so the whole
run finishes in under 5 seconds.

## Detection, recovery, and recovery time -- summary

```text
scenario                  detection                            recovery                           time
duplicate request         DB unique index on idempotency_key   none needed; only one job exists   ~3 s (job runs once)
job timeout (recovers)    Process.waitFor times out             process killed, job retried        ~timeout + 1 attempt
job timeout (gives up)    same, on every attempt                 bounded by max-attempts (3);        3 x timeout
                                                                  FAILED, never retried forever
Redis unavailable         queue.enqueue fails fast (Lettuce's        job accepted anyway (row saved);   until Redis restored +
                          8 s command timeout) and is caught         recovery enqueues it once Redis    one recovery interval
                          in the controller                         is back
database unavailable      Hikari connection timeout (5 s);        503 to new requests meanwhile;      until Postgres restored
                          /readyz reports db DOWN                 the in-flight job's result is       + its own duration
                                                                   written once Postgres is back
worker crash              recovery finds a RUNNING row older      job retried (or failed, budget      one recovery interval
                          than the Python timeout + grace         permitting) by any live worker       past the grace period
partial workflow failure  DispatchOutcome.transientFailure/       retried in-line (transient) or       < 5 s (in-line, no
                          permanentFailure                        cancels only its dependents          queue)
                                                                   (permanent); the rest of the DAG
                                                                   completes
```

## Tests

```text
ForecastRecoveryIntegrationTest         5  real Postgres + Redis: an abandoned RUNNING job is retried and
                                           re-enqueued, with the lost attempt counted; on its last
                                           attempt it FAILs instead of retrying forever; an orphaned
                                           PENDING/RETRYING job with no queue entry is re-enqueued, a
                                           job already in the queue is not duplicated; two sequential
                                           sweeps recover a job exactly once; only one of two claims on
                                           the same id succeeds
ForecastWorkerTest                     +3  a duplicate queue entry never runs a job twice (the second
                                           claim fails); a Redis outage on dequeue never escapes the
                                           poll loop; a database outage mid-attempt leaves the job
                                           RUNNING for recovery, not lost or wrongly marked
WorkflowPartialFailureIntegrationTest    1  the DAG above: transient retried and recovers; permanent
                                           fails once and cancels only its dependents; the independent
                                           branch and upstream nodes still succeed; persisted state
                                           matches after a reload
run_reliability_tests.py                6  the end-to-end scenarios above, against the real running
                                           system (not a test assertion; see ml/artifacts/reliability_tests)
```

`InMemoryForecasts` (a shared test fixture) replaced five near-identical
hand-rolled `ForecastJpaRepository` mocks across the existing forecast
test classes, and now also fakes the unique idempotency index and the
conditional claim, so every one of those tests exercises the same real
constraint the database enforces rather than a looser stand-in.

## What this task does not do

- **No redelivery/visibility-timeout protocol on the queue itself.**
  `ForecastQueue`'s interface and Redis's list semantics are unchanged.
  Recovery works entirely off the database's own `updated_at`, which is
  simpler than a broker-level redelivery mechanism and needed no queue
  migration.
- **No cancel endpoint.** `docs/forecast-api-contract.md` still locks
  the three existing routes; a `CANCELLED` job is still never produced
  by anything in this codebase.
- **The malformed Earth data fixture is FIRMS-only, and analysis-only.**
  ERA5 and static geography have their own existing schema-validation
  tests; this fixture exercises the same "bad
  row fails the whole request cleanly" property for the one input most
  likely to carry a live-scraped bad value. A forecast-pipeline version
  was tried and dropped (see "After" above): it needs a full
  ERA5/geography/model fixture, not just a FIRMS directory.
