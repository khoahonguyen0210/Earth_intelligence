# Structured Logging — LOCKED

This document freezes the structured logging design. It is not a
brainstorming document.

Before this task the backend had **no logging at all**: no logger in
any class, and only Spring's own startup lines in plain text. Every
line is now one JSON object.

## Format: Spring Boot's built-in ECS, not a hand-rolled encoder

```properties
logging.structured.format.console=${LOG_FORMAT:ecs}
```

Spring Boot (4.1.1 here) ships structured logging with Elastic Common
Schema output, so there is no logstash-encoder dependency and no
logback XML. `LOG_FORMAT=logstash` or `gelf` switches formats. There is
deliberately no plain-text fallback, so every environment (tests,
Docker Compose, kind, EKS) emits the same parseable lines.

A real line, copied from the test run's console output:

```json
{"@timestamp":"2026-09-26T04:09:15.821241600Z",
 "log":{"level":"INFO","logger":"com.example.backend.logging.RequestIdFilter"},
 "process":{"pid":29820,"thread":{"name":"main"}},
 "service":{"name":"backend","node":{}},
 "message":"POST /forecasts -> 201",
 "request_id":"99c401f6-f1a1-4f49-b944-fe44e98be150",
 "event":"http_request","http_method":"POST","http_path":"/forecasts",
 "http_status":201,"duration_ms":2,"ecs":{"version":"8.11"}}
```

## The nine fields, and where each comes from

```text
field        source                                           on which lines
timestamp    ECS @timestamp                                   every line
service      ECS service.name <- spring.application.name      every line
level        ECS log.level                                    every line
request ID   MDC request_id  (RequestIdFilter)                everything during an HTTP request
job ID       MDC job_id      (ForecastWorker)                 everything while a forecast job runs,
                                                              plus job_enqueued/job_deduplicated
workflow ID  MDC workflow_id (WorkflowExecutor)               everything during execute()
event        key-value `event`                                every application event (list below)
duration     key-value duration_ms                            http_request, job/analysis/node outcomes
error code   key-value error_code (ErrorCode enum)            every failure event
```

MDC entries and SLF4J fluent key-value pairs both become top-level JSON
fields. Boot's ECS formatter includes them, confirmed by
`StructuredLoggingIntegrationTest` against real console output, not
assumed.

## Events

```text
event                          level   emitted by           extra fields
http_request                   INFO/   RequestIdFilter      http_method, http_path, http_status
                               ERROR*
job_enqueued                   INFO    ForecastController   job_id, idempotency_key_present
job_deduplicated               INFO    ForecastController   job_id, status
job_started                    INFO    ForecastWorker       attempt
job_succeeded                  INFO    ForecastWorker       attempt, duration_ms
job_retry_scheduled            WARN    ForecastWorker       attempt, max_attempts, duration_ms, error_code
job_failed                     ERROR   ForecastWorker       attempt, duration_ms, error_code, transient
job_skipped                    INFO    ForecastWorker       (dequeued id missing or not runnable)
analysis_succeeded             INFO    AnalysisController   analysis_id, operation, duration_ms
analysis_failed                WARN**  AnalysisController   analysis_id, operation, duration_ms, error_code
workflow_node_succeeded        INFO    WorkflowExecutor     task_id, task_type, attempt, duration_ms
workflow_node_retry_scheduled  WARN    WorkflowExecutor     same
workflow_node_failed           ERROR   WorkflowExecutor     same
workflow_finished              INFO    WorkflowExecutor     node_count, succeeded, failed, cancelled

*  ERROR when the response status is >= 500.
** WARN, not ERROR: an analysis failure is almost always the request's
   own fault (unsupported operation, empty region), returned as 422.
```

How the IDs connect: a forecast is created on an HTTP thread and runs
later on the worker thread, so no single ID spans both. The link is the
`job_enqueued` line, which carries the request's `request_id` (MDC) and
the new `job_id` (key-value). Every later worker line for that job
carries the same `job_id`. Analysis runs synchronously on the request
thread, so its lines share the request's `request_id` directly.

## Error codes

`ErrorCode` gives a stable, machine-readable failure *kind*, so log
queries and alerts need not pattern-match free text that embeds paths,
exit codes, and Python messages:

```text
PYTHON_START_FAILED   process could not be started / written to (IOException)   transient
PYTHON_TIMEOUT        exceeded forecast.python.timeout-seconds, killed          transient
PYTHON_INTERRUPTED    waiting thread interrupted                                 transient
PYTHON_FAILED         script exited non-zero: rejected the request or its data  permanent
OUTPUT_PARSE_FAILED   exit 0 but stdout was not the expected JSON                permanent
OUTPUT_READ_FAILED    stdout/stderr could not be read back                       permanent
```

The transient/permanent split is the one already made
(`docs/forecast-retry-and-idempotency.md`). The codes are only added
alongside it. The code lives on `ForecastOutcome`/`AnalysisOutcome`
and is **not** persisted or returned by the API. The human-readable
error text in the database and in the 422 body is unchanged.

## Never log secrets

Two rules, one of them enforced in code:

1. **Nothing sensitive is logged by construction.** No request or
   response bodies, no headers other than the validated request ID, no
   query strings (`http_path` is the path only), no configuration
   values.
2. **Text the backend did not write is redacted.** The backend logs
   the error text of a failed Python subprocess, which it does not
   control. `data/firms.py` builds its request URL with the FIRMS map
   key inside the path (`build_area_url`), so a traceback from a failed
   FIRMS call would print the key into the logs. `SecretRedactor` masks
   every configured secret value (`FIRMS_MAP_KEY`,
   `spring.datasource.password`, `object-store.secret-key`) as `***`
   before such text is logged. It also truncates the text to 2,000
   characters, so one huge traceback cannot flood a line. Values
   shorter than 6 characters are ignored, so an unset or trivial value
   can never mask ordinary words. `ForecastWorkerLoggingTest` feeds a
   real-shaped FIRMS URL containing a key through a failing job and
   asserts that the key is absent from the logged message.

The request ID is the only client-controlled value that reaches a
field, so `RequestIdFilter` accepts a caller's `X-Request-Id` only if it
matches `[A-Za-z0-9._-]{1,64}`. Anything else, such as a newline, is
replaced with a fresh UUID.

## Tests

```text
RequestIdFilterTest                5  id generated/echoed/in MDC and cleared; plain caller id kept;
                                      forged/oversized id replaced; http_request fields; 5xx -> ERROR
SecretRedactorTest                 4  every occurrence masked; blank/short ignored; truncation; null
ForecastWorkerLoggingTest          4  started->succeeded with job_id and duration; permanent failure
                                      -> job_failed + error_code + secret redacted; transient ->
                                      job_retry_scheduled WARN; unknown id -> job_skipped
StructuredLoggingIntegrationTest   1  real app on a random port, real HTTP request: the console
                                      line is valid ECS JSON with timestamp, level, service,
                                      request_id, event, method, path, status, duration_ms
```

Full backend suite after the change: **91 tests, 0 failures** (77 before
this task, plus these 14). The existing controller and worker tests were
updated only for the new constructor argument (`SecretRedactor`) and
the error-code parameter.

## What this task does not do

- **Python-side logging.** The Python pipeline runs as a subprocess per
  job, and its stdout is the result channel (JSON). Its contribution to
  the logs is the backend's job and analysis events, plus its redacted
  error text on failure. A separate Python log stream would have no
  consumer yet.
- **Shipping and querying.** In the cloud, the CloudWatch add-on's Fluent
  Bit ships these lines as-is (`docs/cloud-deployment.md`). Locally,
  `docker compose logs` / `kubectl logs` show them. Metrics (13.2) and
  tracing (13.3) are the next tasks. Tracing's trace IDs will join
  `request_id` on the same lines.
