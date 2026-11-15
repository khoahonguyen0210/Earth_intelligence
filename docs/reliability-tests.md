# Reliability Tests

Seven controlled failures are tested. Six run end to end against the
running system through `scripts/reliability/run_reliability_tests.py`.
The seventh, partial workflow failure, has no HTTP entry point yet
(`WorkflowExecutor` is not connected to a route, see
`docs/workflow-execution.md`), so it is a `@SpringBootTest` against
`WorkflowExecutor` and `WorkflowStore`:
`WorkflowPartialFailureIntegrationTest`.

## What the harness does

`scripts/reliability/run_reliability_tests.py` starts the packaged
backend jar as an OS process, against the `docker compose` Postgres and
Redis, with a stub Python pipeline
(`scripts/reliability/stub_forecast.py`). The stub's behavior depends on
the region name in the request: `sleep-<n>`, `slow-once-<nonce>`,
`hang`, or anything else to succeed at once.

For each scenario, the harness sends HTTP requests, kills the backend
process, stops and restarts the `ai-earth-redis` and `ai-earth-postgres`
containers, and polls `/forecasts/{id}` until the job reaches a final
state or a timeout. The kill is hard (`taskkill /T` on Windows,
`SIGKILL` on the process group elsewhere, with no shutdown hooks), to
stand in for a crashed pod or node. Nothing is mocked. The malformed
Earth data scenario runs `run_analysis_cli.py` and
`run_forecast_cli.py` against a fixture FIRMS history folder with one
corrupt CSV row.

To run it from the repository root, after `docker compose up -d` and
building the backend jar with `./mvnw package -DskipTests`:

```bash
.venv/Scripts/python scripts/reliability/run_reliability_tests.py <label>
```

It writes `ml/artifacts/reliability_tests/<label>.json`, with one
record per scenario (how the failure was detected, how it recovered,
the final result and the recovery time), and prints a summary table.

## Before: three gaps

The first run, on the code before any fix:

```text
PASS  duplicate request           SUCCEEDED       2.9s
PASS  job timeout (recovers)      SUCCEEDED       1.2s
PASS  job timeout (gives up)      FAILED         67.0s
FAIL  Redis unavailable           NOT ACCEPTED    -
FAIL  database unavailable        RUNNING       150.3s
FAIL  worker crash                RUNNING       285.3s
FAIL  malformed Earth data        FAILED         61.4s
```

Three serious gaps:

- **Redis unavailable: the job was lost.** `POST /forecasts` saved the
  row and then called `queue.enqueue` without a guard. A
  `DataAccessException` there left the controller as a plain 500, and
  the client got no forecast id to poll. For the client, the request
  was gone, even though a `PENDING` row existed that nothing would ever
  run.
- **Database unavailable during a job: the job stayed `RUNNING`
  forever.** `ForecastWorker.attempt` wrote `RUNNING` before the job and
  the outcome after it. If the outcome write failed, or the worker died
  in between, nothing ever changed the row again. After 150 s it was
  still `RUNNING`.
- **Worker crash during a job: the job stayed `RUNNING` forever**, for
  the same reason. `docs/forecast-async-jobs.md` had named this gap in
  advance: "a worker that dies between popping an id and finishing the
  job loses that job today -- there is no redelivery or visibility
  timeout." After 285 s it was still `RUNNING`.

The other two failures came from the harness being too strict, not from
product bugs. "Job timeout (gives up)" and "malformed Earth data" failed
only an exact-wording check in the script; both had already reached
`FAILED` for the right reason. The script now checks the meaning
(attempts used up; the error names the bad file) instead of an exact
string.

## The fix: ForecastRecovery and an atomic claim

The following changes closed all three gaps without changing the queue
message format (a bare id) or the `ForecastQueue` interface, except for
one new method.

**1. `Forecast.updated_at` (Flyway `V5`) and an atomic claim.** Every
save sets `updated_at`. `ForecastJpaRepository.claim` is one conditional
`UPDATE ... SET status = 'RUNNING' ... WHERE status IN ('PENDING',
'RETRYING')`. It succeeds only if the row is still waiting, so when two
workers hold the same id (a duplicate queue entry, or a job queued again
while a worker still has it), exactly one runs it. The worker calls
`store.claim` before running anything, instead of always writing
`RUNNING`.

**2. `ForecastRecovery`, a `@Scheduled` sweep on every replica.**
Postgres holds the true state; the Redis list is only a hint of what to
run next. There are two cases, both judged by how long a row has gone
without a change:

```text
abandoned attempt   RUNNING longer than forecast.python.timeout-seconds
                    plus a grace period: the worker died, or its final
                    write failed. Counted as a failed attempt
                    (WORKER_LOST, temporary): RETRYING and queued again
                    while attempts remain, otherwise FAILED, with the
                    same limit as any other retry.
orphaned job        PENDING or RETRYING longer than the threshold AND not
                    in the Redis list: its queue entry was never written
                    (Redis was down at submit time), or a worker took it
                    and then could not run it. Queued again. A job that
                    is only waiting behind a normal backlog is still in
                    the list and is left alone.
```

Every change that recovery makes is also a conditional `UPDATE`, which
succeeds only if the row is still in the state and age that the sweep
saw. So the sweeps of two replicas, or a sweep and a worker that just
took the job, never both act on one job.
`ForecastRecoveryIntegrationTest` checks this: two sweeps in a row over
one abandoned job recover it exactly once.

**3. The worker and the controller handle a dependency outage.**
`ForecastWorker.pollOnce` and `process` catch `DataAccessException`
around the dequeue and around the whole attempt. They log one `WARN` per
outage (not one per 100 ms poll) and wait
(`forecast.worker.error-backoff-ms`) instead of looping fast.
`POST /forecasts` catches the same exception around `queue.enqueue`
only: the row is still saved and `201` is still returned with a
forecast id, and recovery queues the job when Redis is back. When a
dependency failure
(`DataAccessResourceFailureException`, `CannotCreateTransactionException`
or `TransientDataAccessException`) reaches the API, it returns `503`
with `Retry-After` instead of a plain `500`
(`ApiErrorHandler.dependencyUnavailable`). The Postgres connection
timeout is cut from Hikari's default of 30 s to 5 s
(`spring.datasource.hikari.connection-timeout`), so a request fails
quickly enough for a `503` to be useful.

## After: the same scenarios again

```text
PASS  duplicate request           SUCCEEDED       2.3s
PASS  job timeout (recovers)      SUCCEEDED       0.0s
PASS  job timeout (gives up)      FAILED         62.1s
PASS  Redis unavailable           SUCCEEDED      18.9s
PASS  database unavailable        SUCCEEDED      15.9s
PASS  worker crash                SUCCEEDED      89.9s
PASS  malformed Earth data        FAILED          0.0s
```

`ml/artifacts/reliability_tests/final.json` is the run behind this
table. The earlier runs in the same folder (`before`, `after`, `after2`)
are kept as a record of what each fix changed.

Every scenario now recovers or fails cleanly as designed, and the
service stays up throughout. This run found two more issues:

**Lettuce has no command timeout by default.** With Redis stopped
(`docker stop`), the `LPUSH` in `queue.enqueue` blocked for more than a
minute before it failed, far too long for `POST /forecasts` to be a
useful "accepted, try again" response. The fix is
`spring.data.redis.timeout=8000ms`. This value must stay above
`forecast.queue.poll-timeout-seconds` (default 5 s), because the
worker's blocking `RPOP` is meant to wait that long on an empty queue. A
shorter client timeout would fire on every normal idle poll, not only
during an outage.

**An old shared development database changes what a test measures.**
The first rerun of "duplicate request" took more than 60 s instead of
about 3 s, with no product change. `ForecastRecovery` was doing its job:
it picked up dozens of jobs left orphaned by earlier manual runs and
test runs, collected over hours in this one Postgres. Real traffic would
never leave so many at once. The logs confirmed it: `job_requeued`
events for older ids were ahead of the scenario's new job in the same
queue. This is not a product bug. The scenario's wait limit was raised
to 180 s (a backlog is still a backlog, and the job did finish), and the
cause is recorded here.

The forecast part of the malformed-data scenario was dropped. It needs a
full ERA5, geography and model fixture that a FIRMS-only folder cannot
replace, and it hit its own `forecast.python.timeout-seconds` (because
of missing inputs, not the corrupt row) instead of the intended failure.
The analysis part, run on the full pipeline over the corrupt row,
already shows the property this scenario checks. A well-formed request
sent afterward to the same service shows that the corrupt row did not
block anything else.

## Partial workflow failure

`WorkflowPartialFailureIntegrationTest` runs the forecast DAG and an
independent branch through `WorkflowExecutor` against Postgres:

```text
get_data -> validate -> build_features (transient once) -> run_forecast (permanent)
                     \                                        -> get_result_evidence
                      -> calculate_statistics                  -> generate_map
```

`build_features` fails once with a temporary error and succeeds on
retry. The workflow executor's own tests already cover this; here it is
checked again in the larger DAG. `run_forecast` fails permanently. Only
that node is marked `FAILED`; `get_result_evidence` and `generate_map`
are `CANCELLED` without being dispatched; and the independent
`calculate_statistics` branch and every upstream node still reach
`SUCCEEDED`. The workflow is saved and loaded again from Postgres, so
the stored state is checked, not only the state in memory. Retries
happen in place (no queue and no wait between attempts), so the run
finishes in under 5 seconds.

## Detection, recovery and recovery time

```text
scenario                  detection                            recovery                           time
duplicate request         DB unique index on idempotency_key   none needed; only one job exists   ~3 s (job runs once)
job timeout (recovers)    Process.waitFor times out            process killed, job retried        ~timeout + 1 attempt
job timeout (gives up)    same, on every attempt               limited by max-attempts (3);       3 x timeout
                                                               FAILED, never retried forever
Redis unavailable         queue.enqueue fails fast (Lettuce's  job accepted anyway (row saved);   until Redis is back +
                          8 s command timeout) and is caught   recovery queues it once Redis      one recovery interval
                          in the controller                    is back
database unavailable      Hikari connection timeout (5 s);     503 to new requests meanwhile;     until Postgres is back
                          /readyz reports db DOWN              the running job's result is        + the job's own time
                                                               written once Postgres is back
worker crash              recovery finds a RUNNING row older   job retried (or failed, if no      one recovery interval
                          than the Python timeout + grace      attempts remain) by any live       after the grace period
                                                               worker
partial workflow failure  DispatchOutcome.transientFailure/    retried in place (temporary) or    < 5 s (in place, no
                          permanentFailure                     cancels only its dependents        queue)
                                                               (permanent); the rest of the DAG
                                                               completes
```

## Tests

```text
ForecastRecoveryIntegrationTest         5  Postgres + Redis: an abandoned RUNNING job is retried and
                                           queued again, with the lost attempt counted; on its last
                                           attempt it FAILs instead of retrying forever; an orphaned
                                           PENDING/RETRYING job with no queue entry is queued again, a
                                           job already in the queue is not duplicated; two sweeps in a
                                           row recover a job exactly once; only one of two claims on
                                           the same id succeeds
ForecastWorkerTest                     +3  a duplicate queue entry never runs a job twice (the second
                                           claim fails); a Redis outage on dequeue never escapes the
                                           poll loop; a database outage during an attempt leaves the
                                           job RUNNING for recovery, not lost or wrongly marked
WorkflowPartialFailureIntegrationTest    1  the DAG above: the temporary failure is retried and
                                           recovers; the permanent failure cancels only its
                                           dependents; the independent branch and upstream nodes
                                           still succeed; the stored state matches after a reload
run_reliability_tests.py                6  the end-to-end scenarios above, against the running
                                           system (see ml/artifacts/reliability_tests)
```

`InMemoryForecasts`, a shared test fixture, replaced five nearly
identical hand-written `ForecastJpaRepository` mocks in the forecast
tests. It also imitates the unique idempotency index and the
conditional claim, so all those tests check the same rule that the
database enforces, not a looser copy.

## Out of scope

- **No redelivery or visibility timeout in the queue itself.** The
  `ForecastQueue` interface and the Redis list behavior are unchanged.
  Recovery works from the database's `updated_at` alone, which is
  simpler than redelivery in the broker and needed no queue migration.
- **No cancel endpoint.** `docs/forecast-api-contract.md` still defines
  only the three existing routes, so nothing produces a `CANCELLED` job.
- **The malformed-data fixture covers FIRMS and the analysis path
  only.** ERA5 and static geography have their own schema validation
  tests. This fixture checks that one bad row fails the whole request
  cleanly, for the input most likely to contain a bad value from a live
  download. A forecast version was tried and dropped (see "After"
  above), because it needs a full ERA5, geography and model fixture.
