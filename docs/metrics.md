# Metrics — LOCKED

This document freezes the metrics design. It is not a brainstorming
document.

## Export: Micrometer -> Prometheus text at /actuator/prometheus

The locked stack says "Prometheus-compatible metrics". Spring Boot's
actuator already runs Micrometer, so the only addition is the Prometheus
registry (`io.micrometer:micrometer-registry-prometheus`, version
managed by the Boot parent) and exposing the endpoint:

```properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.percentiles-histogram.forecast.job.duration=true
```

Histogram buckets are on for the two latency meters, so percentiles are
computed at query time (`histogram_quantile`) across replicas, not
pre-computed per pod. The endpoint is not public: since an earlier
security change, every actuator endpoint is on the internal management
port 8081, which no
Service or ALB routes (`docs/security-baseline.md`). The backend pod
template carries the conventional `prometheus.io/scrape|path|port`
annotations, so a Prometheus-compatible scraper in the cluster finds it.

A real scrape of the running backend (after one health check and one
unknown-id lookup):

```text
# TYPE forecast_queue_depth gauge
forecast_queue_depth 0.0
# TYPE forecast_worker_busy gauge
forecast_worker_busy 0.0
http_server_requests_seconds_count{error="none",exception="none",method="GET",outcome="CLIENT_ERROR",status="404",uri="/forecasts/{id}"} 1
http_server_requests_seconds_count{error="none",exception="none",method="GET",outcome="SUCCESS",status="200",uri="/actuator/health"} 2
```

## The handbook's eight metrics

```text
handbook item         Prometheus series                                    source
HTTP request count    http_server_requests_seconds_count                   Spring MVC (built in)
HTTP error count      http_server_requests_seconds_count{outcome=          Spring MVC (built in)
                        "CLIENT_ERROR"|"SERVER_ERROR"}
HTTP latency          http_server_requests_seconds_bucket / _sum / _max    Spring MVC (built in)
queue depth           forecast_queue_depth                                 ForecastMetrics gauge -> Redis LLEN
job duration          forecast_job_duration_seconds_*{outcome=             ForecastWorker, per attempt
                        "succeeded"|"retry_scheduled"|"failed"}
job failure count     forecast_job_failures_total{error_code, terminal}    ForecastWorker
worker utilization    forecast_worker_busy (0/1 per replica)               ForecastWorker, around runner.run
model inference time  forecast_python_stage_duration_seconds_*             Python pipeline's own timing
                        {stage="model_inference"}
```

Plus `analysis_duration_seconds_*{outcome, error_code}` for the
synchronous Earth-analysis path, the analysis counterpart of the job
duration.

Useful queries:

```text
HTTP error rate      sum(rate(http_server_requests_seconds_count{outcome="SERVER_ERROR"}[5m]))
p95 HTTP latency     histogram_quantile(0.95, sum by (le, uri) (rate(http_server_requests_seconds_bucket[5m])))
job failures         sum by (error_code) (increase(forecast_job_failures_total{terminal="true"}[1h]))
worker utilization   avg(avg_over_time(forecast_worker_busy[5m]))       -- fraction of time busy, all replicas
mean inference time  rate(forecast_python_stage_duration_seconds_sum{stage="model_inference"}[15m])
                     / rate(forecast_python_stage_duration_seconds_count{stage="model_inference"}[15m])
```

## Decisions

**Queue depth is read live, and is NaN when unknown.** The gauge calls
`ForecastQueue.size()` (Redis `LLEN`, the exact number KEDA scales on)
on every scrape rather than caching a counter that could drift. If Redis
is unreachable, the gauge reports NaN, a gap in the graph, instead of
failing the scrape or claiming an empty queue. That matters for Task
13.5's "Redis unavailable" test: a fake 0 would look like a healthy
idle system.

**Utilization is a busy gauge, not a derived ratio.** The worker is one
scheduled thread per replica, so busy is exactly 0 or 1.
`avg_over_time` of it is the fraction of time that replica spent running
jobs, and averaging across pods gives fleet utilization. It is set in a
`try`/`finally` around `runner.run`, so a runner exception can never
leave it stuck at 1.

**"Model inference time" is measured by the pipeline, not guessed from
outside.** Every forecast re-fits XGBoost inside the Python subprocess
before scoring (`compute_forecast`), so the subprocess's wall time is
mostly imports, data loading and fitting. That makes it the wrong number
for "inference". `run_forecast` now times its own stages with
`time.perf_counter()` and returns them *beside* the result:

```json
{"result": {...unchanged...},
 "timings_ms": {"data_load": ..., "model_fit": ..., "model_inference": ..., "total": ...}}
```

`model_inference` covers `predict_calibrated` on the inference rows
only. `PythonForecastRunner` reads `timings_ms` into
`ForecastOutcome.timingsMs`, and the worker records each stage. The
result shape in `docs/forecast-api-contract.md` is unchanged, and the
timings are never persisted or returned to API clients. Malformed or
missing timings are dropped, not treated as a failure, because they are
observability, not part of the result.

**Closed tag values only.** Every tag has a fixed, small value set:
`outcome`, `error_code` (an already-fixed enum), `terminal`, `stage`
(whitelisted to the four names Python reports), and Spring's templated
`uri` (`/forecasts/{id}`, never the id). No request, id, or user text
can mint a new time series. `analysis.operation` is deliberately
**not** a tag, because a client controls it.

**Failures are counted per attempt, split by `terminal`.** A transient
failure that is retried counts `terminal="false"`. The attempt that ends
the job FAILED counts `terminal="true"`. The handbook's "job failure
count" is the `terminal="true"` series; the other is the early warning
that the retry/timeout/idempotency work's retries are hiding a flaky dependency.

## Tests

```text
ForecastMetricsTest                 4  queue gauge reads the live queue; NaN (not 0) when the queue
                                       throws; success records duration + stage timings, busy is 1
                                       only during the run, unknown stage ignored; transient then
                                       terminal failures counted separately by error code
PythonForecastRunnerTest            +2 timings_ms parsed (malformed entry dropped, result untouched);
                                       no timings -> empty, still success. Existing tests now also
                                       assert PYTHON_FAILED / PYTHON_TIMEOUT / PYTHON_START_FAILED
PrometheusEndpointIntegrationTest   1  real app + live Redis: /actuator/prometheus is text/plain with
                                       HTTP count, latency buckets, outcome tag, queue depth, busy
test_run_forecast.py                +2 compute_forecast fills model_fit/model_inference (inference <
                                       fit); timing does not change the result
```

Backend suite: **98 tests, 0 failures** (91 before). Python forecast
tests: 8 passed.

`PrometheusEndpointIntegrationTest` needs `@AutoConfigureMetrics`:
Spring Boot disables metrics export in `@SpringBootTest` by default, so
without it `/actuator/prometheus` is a 404 in tests while working in
the real application (confirmed by running the app and scraping it,
output above).

## What this task does not do

- **Run a Prometheus server or dashboards.** This task exports metrics
  and makes them discoverable. Storing and graphing them is the
  cluster's scraper's job: Prometheus, or the CloudWatch agent's
  Prometheus mode in the cloud (`docs/cloud-deployment.md`).
- **Python-process metrics.** The pipeline is a short-lived subprocess
  per job, so it has nothing to scrape. Its numbers reach Prometheus
  through the backend, as above.
