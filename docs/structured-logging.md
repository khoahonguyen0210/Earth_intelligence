# Structured Logging

Before this change, the backend had no logging of its own: no logger in
any class, and only Spring's startup lines in plain text. Now every line
is one JSON object.

## Format: Spring Boot's built-in ECS

```properties
logging.structured.format.console=${LOG_FORMAT:ecs}
```

Spring Boot (4.1.1 here) includes structured logging with Elastic
Common Schema (ECS) output, so there is no logstash encoder dependency
and no logback XML. `LOG_FORMAT=logstash` or `gelf` switches the
format. There is no plain-text fallback, on purpose, so every
environment (tests, Docker Compose, kind, EKS) writes the same
machine-readable lines.

A line copied from the console output of a test run:

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

## The nine fields and their sources

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
fields, because Spring Boot's ECS formatter includes them.
`StructuredLoggingIntegrationTest` confirms this against the console
output.

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
** WARN, not ERROR: an analysis failure is almost always caused by the
   request itself (unsupported operation, empty region) and returned
   as 422.
```

How the IDs connect: a forecast is created on an HTTP thread and runs
later on the worker thread, so no single ID covers both. The link is
the `job_enqueued` line, which has the request's `request_id` (MDC) and
the new `job_id` (key-value). Every later worker line for that job has
the same `job_id`. An analysis runs on the request thread, so its lines
share the request's `request_id` directly.

## Error codes

`ErrorCode` gives a fixed, machine-readable kind of failure. Log queries
and alerts then do not need to match free text that contains paths,
exit codes and Python messages:

```text
PYTHON_START_FAILED   process could not be started or written to (IOException)  temporary
PYTHON_TIMEOUT        ran longer than forecast.python.timeout-seconds, killed   temporary
PYTHON_INTERRUPTED    waiting thread interrupted                                temporary
PYTHON_FAILED         script exited non-zero: rejected the request or its data  permanent
OUTPUT_PARSE_FAILED   exit 0 but stdout was not the expected JSON               permanent
OUTPUT_READ_FAILED    stdout/stderr could not be read back                      permanent
```

The split between temporary and permanent is the existing one
(`docs/forecast-retry-and-idempotency.md`); the codes are only added to
it. The code is stored on `ForecastOutcome` and `AnalysisOutcome` and is
**not** saved or returned by the API. The readable error text in the
database and in the 422 body is unchanged.

## Never log secrets

There are two rules, and one is enforced in code:

1. **Nothing sensitive is logged in the first place.** No request or
   response bodies, no headers other than the validated request ID, no
   query strings (`http_path` is the path only) and no configuration
   values.
2. **Text that the backend did not write is redacted.** The backend logs
   the error text of a failed Python subprocess, which it does not
   control. `data/firms.py` puts the FIRMS map key inside the path of its
   request URL (`build_area_url`), so a traceback from a failed FIRMS
   call would print the key into the logs. `SecretRedactor` replaces
   every configured secret value (`FIRMS_MAP_KEY`,
   `spring.datasource.password`, `object-store.secret-key`) with `***`
   before such text is logged. It also cuts the text to 2,000
   characters, so one huge traceback cannot flood a line. Values shorter
   than 6 characters are ignored, so an empty or trivial value can never
   mask ordinary words. `ForecastWorkerLoggingTest` sends a FIRMS URL of
   the real shape, with a key in it, through a failing job and checks
   that the key is not in the logged message.

The request ID is the only value controlled by the client that reaches
a field, so `RequestIdFilter` accepts a caller's `X-Request-Id` only if
it matches `[A-Za-z0-9._-]{1,64}`. Anything else, such as a newline, is
replaced with a new UUID.

## Tests

```text
RequestIdFilterTest                5  id generated/echoed/in MDC and cleared; plain caller id kept;
                                      forged/oversized id replaced; http_request fields; 5xx -> ERROR
SecretRedactorTest                 4  every occurrence masked; blank/short ignored; truncation; null
ForecastWorkerLoggingTest          4  started->succeeded with job_id and duration; permanent failure
                                      -> job_failed + error_code + secret redacted; temporary ->
                                      job_retry_scheduled WARN; unknown id -> job_skipped
StructuredLoggingIntegrationTest   1  full app on a random port, one HTTP request: the console
                                      line is valid ECS JSON with timestamp, level, service,
                                      request_id, event, method, path, status, duration_ms
```

Full backend suite after the change: **91 tests, 0 failures** (77
before, plus these 14). The existing controller and worker tests changed
only for the new constructor argument (`SecretRedactor`) and the
error-code parameter.

## Out of scope

- **Python logging.** The Python pipeline runs as one subprocess per
  job, and its stdout carries the result (JSON). It appears in the logs
  through the backend's job and analysis events, plus its redacted error
  text on failure. A separate Python log stream would have no reader
  yet.
- **Shipping and searching logs.** In the cloud, the Fluent Bit of the
  CloudWatch add-on ships these lines as they are
  (`docs/cloud-deployment.md`). Locally, `docker compose logs` and
  `kubectl logs` show them. Metrics are in `docs/metrics.md` and tracing
  in `docs/tracing.md`; trace IDs appear next to `request_id` on the
  same lines.
