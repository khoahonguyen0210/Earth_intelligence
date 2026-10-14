# Kafka and the Go Forecast Worker

Forecast jobs can be queued on Kafka and run by a worker written in Go,
instead of the Redis list and the in-process Java worker. The backend
picks the queue at startup:

```bash
FORECAST_QUEUE=redis   # default
FORECAST_QUEUE=kafka
```

```text
POST /forecasts -> backend saves the job (Postgres or DynamoDB)
                -> publishes {"job_id": ...} to the forecast-jobs topic
Go worker       -> consumes forecast-jobs (group forecast-workers)
                -> POST backend:8081/actuator/forecastjobs/<job id>
backend         -> claims the job, runs the Python pipeline, saves the result
Go worker       -> commits the offset
```

The Go worker never touches the database or the Python code. It calls
one internal endpoint that runs the job through the same `ForecastWorker`
code the Redis path uses, so claiming, retries, attempt counts, metrics,
tracing and the job store behave the same in both modes.

## The message

Topic `forecast-jobs`, keyed by job ID, so retries of one job stay in
order on one partition:

```json
{"job_id": "05cf52b9-bb49-46a8-948f-4a1e51a3fa0c",
 "enqueued_at": "2026-10-14T03:32:52.043Z",
 "trace_parent": "00-ed93...-7df3...-03"}
```

The backend continues each job's trace from the trace context saved
with the job, so one trace runs from the API request to the Python run.
The worker also forwards `trace_parent` as the `traceparent` header.

## The run endpoint

`POST /actuator/forecastjobs/{id}` is served only on the management port
(8081), which is not exposed publicly, and exists only when
`FORECAST_QUEUE=kafka`.

| Response | Meaning | Worker action |
|---|---|---|
| `200 {"outcome": "ran", "status": ...}` | The job was claimed and run | Commit |
| `200 {"outcome": "skipped", ...}` | Already running, finished or unknown, e.g. a duplicate delivery | Commit |
| `503` | Database, Redis or the object store is down | Retry with backoff, do not commit |
| `400` | Malformed job ID | Dead-letter, commit |

A transient Python failure is retried by the backend as before: the job
goes to `RETRYING` and is published again, up to the attempt limit.

## Delivery guarantees

- **At least once.** An offset is committed only after the backend has
  answered, so a worker that crashes mid-job leaves the message to be
  delivered again.
- **Duplicates are harmless.** The backend claims a job with a
  conditional update, so a second delivery of the same job is reported
  as `skipped` and never runs it twice. Kafka cannot be searched for a
  job, so the recovery sweep republishes any job that has waited longer
  than `FORECAST_RECOVERY_QUEUED_AFTER_SECONDS` (60 s), once per period,
  and relies on the same rule to drop the extra copies.
- **Backend outages pause the worker.** Retryable failures (connection
  errors, timeouts, 429, 5xx) back off from 1 s to 30 s and keep the
  message. Shutdown during a backoff leaves it uncommitted.
- **Poison messages do not block a partition.** Invalid JSON, a bad job
  ID or a 4xx answer sends the message to `forecast-jobs.dlq` with
  `error`, `source_topic` and `source_offset` headers, then commits.
- **Graceful shutdown.** On SIGTERM the worker stops fetching and lets
  the job in progress finish before committing.

## The worker

`worker/` is a Go module (`cmd/forecast-worker`, `internal/jobs`) using
`segmentio/kafka-go`. It runs `WORKER_CONCURRENCY` consumers in one
group, logs JSON with `log/slog`, and serves `/healthz` on `:8090`. The
image is a static binary on distroless (about 18 MB) and runs as a
non-root user.

| Variable | Default |
|---|---|
| `KAFKA_BROKERS` | `localhost:9094` |
| `KAFKA_TOPIC`, `KAFKA_GROUP` | `forecast-jobs`, `forecast-workers` |
| `KAFKA_DLQ_TOPIC` | `forecast-jobs.dlq` |
| `BACKEND_RUN_URL` | `http://localhost:8081/actuator/forecastjobs` |
| `WORKER_CONCURRENCY` | `2` |
| `RUN_TIMEOUT` | `15m` |

Backend settings: `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_FORECAST_TOPIC`,
`KAFKA_FORECAST_GROUP`, `KAFKA_FORECAST_PARTITIONS` (3) and
`KAFKA_CREATE_TOPIC` (true). The backend creates the topic at startup,
and its `forecast.queue.depth` metric is the consumer group's lag.

## Running it

```bash
cd infra/docker
FORECAST_QUEUE=kafka docker compose --profile kafka up -d --build
```

This adds Kafka (KRaft, one node) and the Go worker to the stack. It
combines with `FORECAST_STORE=dynamodb`.

## Tests

| Test | Covers |
|---|---|
| `worker/internal/jobs/*_test.go` | Message validation, HTTP status handling, retry and backoff, dead letters, commit and shutdown behaviour |
| `kafka_integration_test.go` (`-tags integration`) | A real broker: a job is delivered, survives one 503, runs once and is committed |
| `KafkaForecastQueueTest`, `KafkaForecastQueueIntegrationTest` | Publishing, failures and timeouts, consumer lag |
| `ForecastJobsEndpointTest`, `KafkaModeIntegrationTest` | The run endpoint, and the full backend in Kafka mode on a real broker |

```bash
cd worker
go test -race ./...
go test -race -tags integration ./...   # needs Kafka on localhost:9094
```
