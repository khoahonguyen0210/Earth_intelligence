# Forecast Retry, Timeout, and Idempotency — LOCKED

This document freezes retry/timeout/idempotency behavior per Task 6.6 of
the Execution Handbook. It is not a brainstorming document. It builds on
`docs/forecast-async-jobs.md` (Task 6.5) rather than redefining it.

The handbook lists four rules; each maps to one concrete mechanism below.

## `transient dependency error -> retry`

`ForecastOutcome` now carries a `transientFailure` flag alongside
`success`/`result`/`error`. `PythonForecastRunner` sets it when the
problem is with reaching/running the dependency, not with the request:

```text
transient  -- couldn't start/write to the Python process (IOException)
transient  -- the process exceeded forecast.python.timeout-seconds and
              was killed (see "worker timeout" below)
transient  -- the runner thread was interrupted
permanent  -- the process exited non-zero (the request/data produced an
              error the Python side reported)
permanent  -- the process's stdout wasn't parseable JSON (a contract
              bug, not something a retry fixes)
```

`ForecastWorker` is the only thing that reads the flag: on a transient
outcome with attempts remaining, it re-enqueues the same forecast id
instead of finishing the job.

## `invalid request/data -> fail without infinite retry`

A permanent outcome (`transientFailure() == false`) goes straight to
`FAILED` on the very first attempt, regardless of
`forecast.worker.max-attempts` -- `ForecastWorker` only ever retries a
transient outcome. This is what keeps a bad request (an unresolvable
region, a model that can't fit the given data) from being retried at
all, let alone infinitely.

## `same idempotency key -> one logical job`

`POST /forecasts` accepts an optional `Idempotency-Key` header (not a
body field -- `docs/forecast-api-contract.md`'s request shape,
`region`+`cutoff`, is unchanged). A header is looked up against
`forecasts.idempotency_key` (added by
`V2__forecast_retry_and_idempotency.sql`, a partial unique index so rows
without a key don't collide with each other):

```text
no header, or key not seen before  -> normal 201 Created, new PENDING job
key matches an existing forecast   -> 200 OK, that forecast's current
                                       {forecast_id, status} -- no new
                                       row, nothing re-enqueued
```

A race between two requests carrying the same new key is closed by the
database, not by application-level locking: both attempt the insert,
the unique index lets exactly one through, and the loser catches
`DataIntegrityViolationException` and re-reads the winner's row to
return it -- still exactly one logical job either way.

## `worker timeout -> recover/retry`

`PythonForecastRunner` waits on the subprocess with
`Process.waitFor(forecast.python.timeout-seconds, SECONDS)` rather than
the unbounded `waitFor()` Task 6.2 used. On expiry it calls
`process.destroyForcibly()` (recovering the resource -- the process does
not linger) and returns a transient outcome, which `ForecastWorker`
retries like any other transient failure.

stdout/stderr are drained on two background daemon threads started
before the timed wait, not read sequentially after it: a process whose
combined output exceeds the OS pipe buffer blocks on its own write call
until something reads, so waiting for exit before reading at all would
deadlock (and then "time out") on any sufficiently large forecast
payload -- a full California grid `FeatureCollection` easily qualifies.
Killing the process on timeout also unblocks those reader threads (a
plain blocking `InputStream.read()` doesn't respond to interruption, but
does return once the pipe it's reading is closed).

## What this document does not define

There is no backoff delay between retries -- a retried job is
re-enqueued immediately, going through `RETRYING` in between. No
idempotency-key expiry/cleanup exists; a key is unique for the life of
its row, same as everything else already kept indefinitely in Postgres.
Cancelling a queued/running job (`CANCELLED`) is still not implemented --
`docs/forecast-api-contract.md` locks the three existing routes and adding
a cancel endpoint is out of scope here.
