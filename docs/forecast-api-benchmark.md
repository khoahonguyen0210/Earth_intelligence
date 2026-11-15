# Forecast API Benchmark

This benchmark measures the API described in
`docs/forecast-api-contract.md` through
`docs/forecast-retry-and-idempotency.md`. It does not change the API.

## Workload

```text
endpoint:       POST /forecasts
request body:   {"region": {"kind": "named", "value": "california"},
                 "cutoff": "2024-08-15T10:00:00Z"}
request count:  50
concurrency:    1 (sequential)
```

One endpoint and one fixed body are sent one after another to a
backend running locally (`docker compose up -d` in `infra/docker/`, then
the Spring Boot app). `POST /forecasts` is the main endpoint of the
forecast API, and its cost depends only on the API.
`GET /forecasts/{id}` and `.../result` would also include whatever the
background Python job is doing, which is a different measurement.

The requests are sequential, not concurrent. This is a baseline for the
cost of one request on one instance (routing, validation, one Postgres
insert and one Redis `LPUSH`), taken before any optimization. It is not
a load test; that can come later, once there is something to compare it
with.

Each successful call creates a `PENDING` forecast row and queues a job,
and `ForecastWorker` picks these up in the background like any other
request. A run on a local stack leaves 50 jobs to process afterward
(they may fail quickly if no trained model is set up locally). That
background work is not part of the measurement.

## Metrics

```text
p50 / p95 / p99 latency   per-request wall-clock time, nearest rank
                          (api.benchmark.latency_percentile)
throughput                successful requests / total wall-clock time
error rate                non-201 or failed requests / request count
```

## Files

```text
ml/src/.../api/benchmark.py   run_api_benchmark and ApiBenchmarkResult
                              (unit-tested: tests/api/test_api_benchmark.py)
scripts/api/benchmark_forecast_api.py
                              thin driver that sends HTTP requests to
                              FORECAST_API_BASE_URL (default
                              http://localhost:8080); not unit-tested,
                              like the other scripts under scripts/
data/processed/benchmark/forecast_api_benchmark.json
                              raw results and summary in one file (the
                              percentiles, throughput and error rate are
                              the summary); ignored by git and can be
                              rebuilt, like pipeline_benchmark.json
```

## Result

A run against the local stack (50/50 succeeded):

```text
p50: 44ms   p95: 66ms   p99: 574ms
throughput: 17.9 req/s
error rate: 0.0
```

## Out of scope

Making the API faster than this baseline is out of scope; this
benchmark only records the starting point. Other endpoints, a
concurrent load test, and the full job latency (from creation to a
final status) are separate measurements that could be added later.
