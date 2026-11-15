# Forecast Async Jobs

This document describes the async forecast jobs that run through Redis.
It builds on `docs/forecast-api-contract.md` and
`docs/persistence-schema.md` and does not change either.

Infrastructure: `infra/docker/docker-compose.yml` runs `redis:7-alpine` on
port `6379`, no auth (matching the other local dev services). Run
`docker compose up -d` from `infra/docker/` before running the backend or
`RedisForecastQueueTest`, the same as Postgres/MinIO.

## The flow

```text
POST /forecasts
  -> ForecastController creates a Forecast row, status PENDING (durable,
     the Postgres-backed ForecastStore)
  -> ForecastController pushes the forecast id onto a Redis list
     (ForecastQueue/RedisForecastQueue)
  -> ForecastWorker, polling on a fixed schedule, blocking-pops the next
     id (Redis RPOP with a timeout)
  -> ForecastWorker flips the row to RUNNING, calls the existing
     ForecastRunner (still one synchronous Python subprocess per job --
     only the caller moved), then flips it to a terminal status
  -> GET /forecasts/{id} and GET /forecasts/{id}/result read whatever the
     row currently says, same as before
```

`ForecastController` no longer calls `ForecastRunner`. It only writes
the PENDING row and queues the job. `ForecastWorker` is the only caller
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
job today -- there is no redelivery or visibility timeout. That gap and
the use of `RETRYING` are handled later, in
`docs/forecast-retry-and-idempotency.md` and `docs/reliability-tests.md`.

## States

```text
PENDING | RUNNING | SUCCEEDED | FAILED | RETRYING | CANCELLED
```

`Forecast.Status` now has all six, matching
`docs/forecast-api-contract.md`. The flow above produces `PENDING` and
`RUNNING`. `RETRYING` (retry a transiently
failed job) and `CANCELLED` (cancel a queued/running job) are defined so
the set of states is complete, but nothing produces either yet. Retry
policy, timeouts and idempotency are added later. There is no cancel
endpoint, because `docs/forecast-api-contract.md` defines only the
three existing routes.

## Result endpoint behavior for a non-terminal forecast

`docs/forecast-api-contract.md` only specifies
`GET /forecasts/{id}/result` for a terminal (`SUCCEEDED`/`FAILED`)
forecast, because no other status could occur before this change. Now
that `PENDING` and `RUNNING` occur, fetching a result before it exists returns
`409 Conflict` with the same `{"error": "<message>"}` shape the `422`
failure case already uses, rather than `200` with a null result:

```json
{ "error": "forecast <id> has not finished (status: RUNNING)" }
```

## Out of scope

Retry after a temporary failure, worker timeouts and idempotency keys
are not part of this step; `RETRYING` exists only as an enum value. The generic `jobs` table `docs/persistence-schema.md` describes
stays schema-only: `forecasts` already is the durable job record for this
flow (its own id, status and error), so no second job row is added for
the same request.
