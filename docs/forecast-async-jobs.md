# Forecast Async Jobs — LOCKED

This document freezes the Redis-backed async job design per Task 6.5 of
the Execution Handbook. It is not a brainstorming document. It builds on
`docs/forecast-api-contract.md` (Task 6.1) and `docs/persistence-schema.md`
(Task 6.3) rather than redefining either.

Infrastructure: `infra/docker/docker-compose.yml` runs `redis:7-alpine` on
port `6379`, no auth (matching the other local dev services). Run
`docker compose up -d` from `infra/docker/` before running the backend or
`RedisForecastQueueTest`, the same as Postgres/MinIO.

## The flow

```text
POST /forecasts
  -> ForecastController creates a Forecast row, status PENDING (durable,
     Task 6.3's Postgres-backed ForecastStore)
  -> ForecastController pushes the forecast id onto a Redis list
     (ForecastQueue/RedisForecastQueue)
  -> ForecastWorker, polling on a fixed schedule, blocking-pops the next
     id (Redis RPOP with a timeout)
  -> ForecastWorker flips the row to RUNNING, calls the existing Task 6.2
     ForecastRunner (still one synchronous Python subprocess per job --
     only the caller moved), then flips it to a terminal status
  -> GET /forecasts/{id} and GET /forecasts/{id}/result read whatever the
     row currently says, same as before Task 6.5
```

`ForecastController` no longer calls `ForecastRunner` at all -- it only
writes the PENDING row and enqueues. `ForecastWorker` is the only caller
of `ForecastRunner` now.

## The queue

```java
public interface ForecastQueue {
    void enqueue(String forecastId);
    Optional<String> dequeue();
}
```

`RedisForecastQueue` is a single Redis list (`forecast.queue.key`, default
`forecast-jobs`) used FIFO: `enqueue` is `LPUSH`, `dequeue` is a blocking
`RPOP` with a timeout (`forecast.queue.poll-timeout-seconds`, default 5).
`ForecastWorker.pollOnce` is `@Scheduled(fixedDelay = 100)`; because
`dequeue` already blocks for up to the poll timeout when the queue is
empty, this is a continuous blocking-poll loop, not a busy-wait, and
needs no dedicated worker thread.

A worker that dies between popping an id and finishing the job loses that
job today -- there is no redelivery or visibility timeout. That gap, and
the resulting use of `RETRYING`, is explicitly Task 6.6's scope (see
below), not this one's.

## States

```text
PENDING | RUNNING | SUCCEEDED | FAILED | RETRYING | CANCELLED
```

`Forecast.Status` now has all six, matching
`docs/forecast-api-contract.md`. `PENDING` and `RUNNING` are real and
reachable, driven by the flow above. `RETRYING` (retry a transiently
failed job) and `CANCELLED` (cancel a queued/running job) are defined so
the state space is complete, but nothing produces either yet -- retry
policy, timeouts, and idempotency are Task 6.6's job. There is no cancel
endpoint; adding one is out of scope here since
`docs/forecast-api-contract.md` locks the three existing routes.

## Result endpoint behavior for a non-terminal forecast

`docs/forecast-api-contract.md` only specifies
`GET /forecasts/{id}/result` for a terminal (`SUCCEEDED`/`FAILED`)
forecast, since before this task no other status was reachable. Now that
`PENDING`/`RUNNING` are real, fetching a result before it exists returns
`409 Conflict` with the same `{"error": "<message>"}` shape the `422`
failure case already uses, rather than `200` with a null result:

```json
{ "error": "forecast <id> has not finished (status: RUNNING)" }
```

## What this document does not define

Retry-on-transient-failure, worker timeouts, and idempotency keys
(Task 6.6) are not implemented here -- `RETRYING` exists as an enum value
only. The generic `jobs` table `docs/persistence-schema.md` describes
stays schema-only: `forecasts` already is the durable job record for this
flow (its own id/status/error), so this task does not add a second,
parallel job row for the same request.
