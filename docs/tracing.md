# Tracing — LOCKED

This document freezes the tracing design. It is not a brainstorming
document.

The required chain:

```text
HTTP → job → workflow → worker → storage → result
```

## Stack: Micrometer Tracing over OpenTelemetry, exported as OTLP

The locked stack says "OpenTelemetry tracing". Spring Boot 4.1.1 ships it
as one starter, `spring-boot-starter-opentelemetry`: the OpenTelemetry
SDK, Micrometer Tracing's OTel bridge, W3C trace-context propagation and
an OTLP span exporter. Application code uses only Micrometer Tracing's
vendor-neutral API, in one class (`tracing/Spans`). There is no agent
and no bytecode instrumentation.

```properties
management.tracing.sampling.probability=${TRACING_SAMPLING_PROBABILITY:1.0}
management.observations.enable.tasks.scheduled=false
management.observations.enable.lettuce=false
management.otlp.metrics.export.enabled=false
```

**OTLP carries traces only.** The starter also brings Micrometer's OTLP
*metrics* registry. Left on, it pushes every meter to
`localhost:4318/v1/metrics` each minute whether or not anything listens
(the first live run logged `Publishing metrics for OtlpMeterRegistry
every 1m`). Metrics stay Prometheus-pull as already locked, so
that registry is off. `TracingIntegrationTest` asserts that the real
meter wiring has a Prometheus registry and no OTLP one.

**Export only when an endpoint is set.** Boot creates the OTLP exporter
only when an endpoint is configured, and it maps the standard
OpenTelemetry variables onto its own properties. So a deployment sets:

```text
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://<collector>:4318/v1/traces
```

With no endpoint (tests, a bare `java -jar`), spans are still created
and log lines still carry `traceId`/`spanId`, but nothing is sent
anywhere and nothing logs connection errors. The compose stack sets the
endpoint to its Jaeger service. The kind manifests do not set it because
kind has no collector. The cloud ConfigMap points it at the CloudWatch
agent's OTLP receiver, the same add-on that already ships logs and
metrics (`docs/cloud-deployment.md`, gap 8).

**Sample everything.** Forecast jobs are few and slow (seconds of
Python per job), and a job's trace is the only per-job record of where
its time went. Sampling is parent-based, so a whole job trace is kept or
dropped as a unit. `TRACING_SAMPLING_PROBABILITY` lowers it if volume
ever makes that costly.

## The one real problem: the queue

A forecast is created on an HTTP thread and run later by
`ForecastWorker` on its scheduled thread, possibly on another replica.
The Redis queue carries only the forecast id. Nothing of the request's
trace context survives the hop, so without help every job would start
an unrelated trace. This is the same gap already noted for
`request_id`.

The fix: **the forecast row carries the submitting span's W3C
`traceparent`** (`forecasts.trace_parent`, Flyway `V4`). The worker
reads the row anyway, and continues that trace for every attempt.

Why the row and not the queue message:

- **Rollout-safe.** Changing the Redis message from a bare id to an
  envelope would make an old replica, mid-rollout, dequeue a JSON
  envelope, fail to find it as an id, skip it, and leave the job stuck
  PENDING. A new nullable column is invisible to old code
  (`ddl-auto=validate` ignores extra columns).
- **Retries stay in the trace.** A retry re-enqueues the same id, and
  the row still holds the original traceparent. Every attempt is a
  sibling under the one submit span.
- **The link persists.** A forecast row names the trace of the request
  that created it, long after the logs have rotated.
- **No interface churn.** `ForecastQueue` is unchanged, and so is
  KEDA's `LLEN`.

A row with no traceparent (written before V4, or while nothing was being
traced) starts a new trace for the job. That is not an error.

## Spans

```text
span                                   where                     parent
http post /forecasts                   Spring MVC (built in)     caller's traceparent, else root
  forecast.store.find_by_idempotency_key  ForecastStore          (only with Idempotency-Key)
  forecast.job.submit                  ForecastController        HTTP span
    forecast.store.save  PENDING       ForecastStore             submit
    forecast.queue.enqueue             RedisForecastQueue        submit
  forecast.job.attempt  (1 per attempt) ForecastWorker           submit, via forecasts.trace_parent
    forecast.store.save  RUNNING       ForecastStore             attempt
    forecast.python                    PythonForecastRunner      attempt
    forecast.store.save  SUCCEEDED/FAILED/RETRYING               attempt   <- the result
    forecast.queue.enqueue             (retry only)              attempt
workflow.execute                       WorkflowExecutor          current span, else root
  workflow.node  (1 per node attempt)  WorkflowExecutor          workflow.execute
object_store.put|get|exists|delete     S3ObjectStore             current span only
```

How the six hops map:

```text
HTTP      http post /forecasts (Spring's server observation)
job       forecast.job.submit, tagged job.id
workflow  workflow.execute / workflow.node -- see "What this task does not do"
worker    forecast.job.attempt + forecast.python
storage   forecast.store.*, forecast.queue.enqueue, object_store.*
result    the attempt's final forecast.store.save, tagged forecast.status
```

Tags: `job.id`, `job.attempt`, `job.outcome`
(`succeeded`/`retry_scheduled`/`failed`), `error.code` (the same
`ErrorCode` already established), `forecast.status`, `db.system` (`postgresql`/`redis`),
`queue.key`, `python.<stage>_ms` (the pipeline's own `timings_ms`:
`data_load`, `model_load`, `model_inference`, `total`), `workflow.id`,
`workflow.task_id`, `workflow.task_type`, `workflow.attempt`,
`workflow.node_status`, `object_store.bucket`, `object_store.key`.

### Rules `Spans` enforces

- **Child spans never start a trace.** Store, queue, Python and object
  store calls are recorded only inside a trace that is already running.
  Outside one they run untraced, so a stray call never becomes a
  one-span orphan trace.
- **A failure that is an outcome is still a failed span.** A Python
  exit code or a failed workflow node is not an exception, but its span
  gets error status all the same (`Spans.fail`). The error is recorded
  without a stack trace, which would only point at `Spans.fail` itself.
- **Nothing sensitive reaches a span.** A trace backend is as readable
  as the logs are, so the same logging rules carry over. The attempt span's
  error text is the same `SecretRedactor`-redacted text as the
  `job_failed` log line. `forecast.python` records only the error code,
  never the raw Python/stderr text. Tags hold ids, codes, statuses and
  timings, never request bodies or configuration values.
  `ForecastTracingTest` pushes a real-shaped FIRMS URL containing a key
  through a failing job and asserts the key appears in no span.

### Quiet when idle

Boot automatically observes every `@Scheduled` run and every Lettuce
Redis command. An idle worker's one-second blocking poll therefore
exported a trace per poll per replica: `task forecastWorker.pollOnce`,
`brpop`, `hello`, `client`… `TracingIntegrationTest` caught it. Both
automatic observations are off (the two `management.observations.enable`
lines above). The work they would have shown is already inside real
traces as `forecast.job.attempt` and `forecast.queue.enqueue`. The
dequeue poll is deliberately not a span. This also drops those two
observations' automatic timers (`tasks_scheduled_execution_*`,
`lettuce_*`), which none of the already-locked metrics use.

## Logs and traces join

Micrometer Tracing puts the current span's ids into the MDC, and Boot's
ECS formatter writes them on every line. So every log line written
inside a span carries `traceId` and `spanId`, next to the already-
established `request_id`/`job_id`. Because the worker continues the request's trace,
its `job_*` lines carry **the HTTP request's traceId**. One id now finds
a job's request line, every worker line for every attempt, and the
trace itself. `request_id` alone could not do that across the queue.

## Live run

The backend jar on port 8081, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` pointed
at the compose Jaeger, real Postgres and Redis. Each tree below is
Jaeger's stored copy of one trace, read back through its query API
(`GET /api/v3/traces/<traceId>`; Jaeger v2.21 no longer serves the
legacy `/api/traces`). Durations are Jaeger's.

**A succeeded job** (worker running `timed_forecast_stub.py`, since the
trained production model is not built on this machine):

```text
trace dcf78819f7e07018633be940c81592f1 - 8 spans
http post /forecasts                          736.6 ms  status=201
  forecast.job.submit                         388.4 ms  job.id=ee747f05-...
    forecast.store.save                       335.5 ms  forecast.status=PENDING
    forecast.queue.enqueue                     20.4 ms  queue.key=tracing-demo
    forecast.job.attempt                      335.0 ms  job.attempt=1, job.outcome=succeeded
      forecast.store.save                      32.7 ms  forecast.status=RUNNING
      forecast.python                         264.2 ms  python.model_inference_ms=4.25
      forecast.store.save                      31.9 ms  forecast.status=SUCCEEDED
```

The first PENDING save is the JVM's first JPA write. The HTTP thread's
`job_enqueued` line and the worker thread's `job_started`/`job_succeeded`
lines all carry `traceId` `dcf78819f7e07018633be940c81592f1`.

**A failed job, the real pipeline** (`scripts/query/run_forecast_cli.py`
on the real FIRMS/ERA5 history, no trained model):

```text
trace 988b11d7b14ffcaef4c96cae509315a4 - 8 spans
http post /forecasts                         1762.4 ms  status=201
  forecast.job.submit                        1234.4 ms  job.id=4fa718bf-...
    forecast.store.save                      1179.3 ms  forecast.status=PENDING
    forecast.queue.enqueue                      7.4 ms
    forecast.job.attempt                   118475.4 ms ERROR  job.outcome=failed, error.code=PYTHON_FAILED
      forecast.store.save                     117.0 ms  forecast.status=RUNNING
      forecast.python                      118183.0 ms ERROR  error.code=PYTHON_FAILED
      forecast.store.save                     122.5 ms  forecast.status=FAILED

forecast.job.attempt status  "PYTHON_FAILED: no trained production model at
                              ml\artifacts\production_model_v1 -- run
                              scripts/models/train_production_model.py first"
forecast.python status       "PYTHON_FAILED"   (code only, by design)
```

This is the kind of thing tracing exists to show. The job spent 118 s
inside Python, within 2 s of the 120 s `forecast.python.timeout-seconds`,
before it failed on a check that needs no data: the pipeline loads the
real history before it looks for the model.

## Tests

```text
SpansTest                  9  child untraced outside a trace; root/child parenting; W3C
                              traceparent of the current span; continued joins the stored
                              trace; missing/garbage traceparent -> new trace; typed tags;
                              fail -> ERROR, message, no stack frames; exception -> ERROR +
                              rethrow; noop
ForecastTracingTest        5  controller+store+worker on the real OTel bridge: one trace from
                              the HTTP span to the stored result, with statuses PENDING ->
                              RUNNING -> SUCCEEDED; retries are sibling attempts, the failed
                              one ERROR with error.code; a secret never reaches a span; a
                              legacy row starts its own trace; idle/skipped -> no spans
PythonForecastRunnerTest  +2  forecast.python is a child span tagged with the stage timings;
                              a failed run's span carries only the error code
RedisForecastQueueTest    +1  real Redis: enqueue is a child span tagged redis + queue key;
                              dequeue is not a span
WorkflowTracingTest        3  one workflow.execute span, a workflow.node child per attempt in
                              execution order (retry visible); a failed node fails both spans;
                              a run inside another span joins its trace
TracingIntegrationTest     3  the real app on a random port, real Postgres/Redis/Python stub,
                              the production exporter wiring (@AutoConfigureTracing) into
                              memory: Spring's own server span -> submit -> PENDING save +
                              enqueue -> attempt (continued from the row) -> python -> result
                              save, and the worker's job_succeeded log line carries the
                              request's traceId and the attempt's spanId; an idle worker
                              exports nothing; metrics are Prometheus, not OTLP-pushed
```

Full backend suite after the change: **121 tests, 0 failures** (98
before this task). The existing tests changed only to pass the new
`Spans` constructor argument (`Spans.noop()`) and the new
`ForecastEntity` column.

## What this task does not do

- **Workflows are not on the forecast path yet.** `WorkflowExecutor` is
  traced and tested, but no caller runs it in production:
  `docs/workflow-execution.md` leaves wiring it to a real dispatcher to
  later work. The forecast trace therefore goes HTTP → job → worker
  directly. When a workflow does run, its spans join whatever trace is
  current, so an HTTP-triggered workflow will appear under that request
  with no further change.
- **The Python process is not itself traced.** It is a short-lived
  subprocess whose stdout is the result channel. Its stage timings
  become tags on `forecast.python` rather than child spans. Running an
  OTel SDK inside every subprocess, plus a `TRACEPARENT` hand-off, would
  add startup cost to every job for data the timings already give.
- **No JDBC/Redis driver-level spans.** `forecast.store.*` and
  `forecast.queue.enqueue` are the storage spans. Statement-level JDBC
  spans would need a third-party datasource proxy.
- **Analysis requests** get Spring's HTTP server span only. The
  synchronous analysis path is not part of the chain.
