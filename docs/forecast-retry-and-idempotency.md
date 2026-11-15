# Forecast Retry, Timeout and Idempotency

This document describes how forecast jobs handle retries, timeouts and
duplicate requests. It builds on `docs/forecast-async-jobs.md`.

There are four rules, and each has one mechanism below.

## Temporary dependency error -> retry

`ForecastOutcome` has a `transientFailure` flag next to `success`,
`result` and `error`. `PythonForecastRunner` sets it when the problem is
in reaching or running the dependency, not in the request:

```text
temporary  could not start or write to the Python process (IOException)
temporary  the process ran longer than forecast.python.timeout-seconds
           and was killed (see "Worker timeout" below)
temporary  the runner thread was interrupted
permanent  the process exited with a non-zero code (the Python side
           reported an error caused by the request or the data)
permanent  the process's stdout was not valid JSON (a contract bug
           that a retry will not fix)
```

`ForecastWorker` is the only reader of the flag. For a temporary failure
with attempts left, it queues the same forecast id again instead of
finishing the job.

## Invalid request or data -> fail without endless retries

A permanent failure (`transientFailure() == false`) goes straight to
`FAILED` on the first attempt, whatever `forecast.worker.max-attempts`
is, because `ForecastWorker` retries only temporary failures. So a bad
request (a region that cannot be resolved, or a model that cannot fit
the data) is not retried at all.

## Same idempotency key -> one job

`POST /forecasts` accepts an optional `Idempotency-Key` header. It is a
header, not a body field, so the request shape in
`docs/forecast-api-contract.md` (`region` and `cutoff`) is unchanged.
The key is looked up in `forecasts.idempotency_key`, which
`V2__forecast_retry_and_idempotency.sql` adds with a partial unique
index, so rows without a key do not conflict with each other:

```text
no header, or a new key           -> 201 Created, new PENDING job
key matches an existing forecast  -> 200 OK with that forecast's current
                                     {forecast_id, status}; no new row
                                     and nothing queued again
```

When two requests with the same new key arrive at once, the database
settles it, not locks in the application. Both try to insert, the
unique index lets exactly one through, and the other catches
`DataIntegrityViolationException` and returns the winner's row. Either
way there is one job.

## Worker timeout -> recover and retry

`PythonForecastRunner` waits for the subprocess with
`Process.waitFor(forecast.python.timeout-seconds, SECONDS)` instead of
the unlimited `waitFor()` used before. When the time runs out, it calls
`process.destroyForcibly()`, so the process does not linger, and returns
a temporary failure, which `ForecastWorker` retries like any other.

stdout and stderr are read on two background daemon threads that start
before the timed wait, not one after the other once the process ends. A
process whose output is larger than the OS pipe buffer blocks on its own
write until something reads it. Waiting for the process to exit before
reading would therefore deadlock, and then time out, on any large
forecast; a full California grid `FeatureCollection` is large enough.
Killing the process on timeout also frees those reader threads: a
blocking `InputStream.read()` ignores interruption but returns once its
pipe is closed.

## Out of scope

There is no delay between retries; a retried job is queued again at
once and passes through `RETRYING` on the way. Idempotency keys do not
expire and are not cleaned up; a key stays unique for the life of its
row, like everything else kept in Postgres. Cancelling a queued or
running job (`CANCELLED`) is not implemented, because
`docs/forecast-api-contract.md` defines only the three existing routes.
