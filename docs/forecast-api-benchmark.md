# Forecast API Benchmark — LOCKED

This document freezes the API benchmark. It is not a brainstorming
document. It measures the API `docs/forecast-api-contract.md` through
`docs/forecast-retry-and-idempotency.md` already built,
rather than adding to it.

## Workload (fixed)

```text
endpoint:       POST /forecasts
request body:   {"region": {"kind": "named", "value": "california"},
                 "cutoff": "2024-08-15T10:00:00Z"}
request count:  50
concurrency:    1 (sequential)
```

One endpoint, one fixed body, run sequentially against a locally running
backend (`docker compose up -d` in `infra/docker/`, then the Spring Boot
app). `POST /forecasts` is the one endpoint this whole phase was built
around, and the only one whose cost is a pure, repeatable API concern:
`GET /forecasts/{id}` and `.../result` would fold in whatever the
background Python job happens to be doing, which is a
different thing to measure, not this baseline.

Sequential, not concurrent: this is a single-instance baseline of the
API's own per-request cost (routing, validation, one Postgres insert, one
Redis `LPUSH`), the number this benchmark exists to capture before any
optimization work, not a concurrency/load-limit test -- that question
belongs to a future task, once there is something to compare it against.

Each successful call creates a real `PENDING` forecast row and enqueues a
real job -- `ForecastWorker` picks these up in the background
exactly as it would for any other request. Running this benchmark
against a real local stack is expected to leave 50 real (likely
quick-failing, if no trained model artifact is wired up locally) jobs to
drain afterward; that background work is not part of what this benchmark
measures.

## Metric (fixed)

```text
p50 / p95 / p99 latency  -- per-request wall-clock time, nearest-rank
                             (api.benchmark.latency_percentile)
throughput                -- successful requests / total wall-clock time
error rate                -- non-201 or failed requests / request count
```

## Result

```text
ml/src/.../api/benchmark.py   -- run_api_benchmark / ApiBenchmarkResult
                                  (unit-tested: tests/api/test_api_benchmark.py)
scripts/api/benchmark_forecast_api.py
                               -- thin driver: real HTTP calls against
                                  FORECAST_API_BASE_URL (default
                                  http://localhost:8080), not unit-tested
                                  itself, same as every other real-caller
                                  script under scripts/
data/processed/benchmark/forecast_api_benchmark.json
                               -- raw + summary result (one file; the
                                  percentiles/throughput/error rate ARE
                                  the summary). Gitignored, same as
                                  pipeline_benchmark.json -- a
                                  regenerable local artifact, not tracked
                                  state.
```

A real run against the local stack (50/50 succeeded):

```text
p50: 44ms   p95: 66ms   p99: 574ms
throughput: 17.9 req/s
error rate: 0.0
```

## What this document does not define

Optimizing the API to improve on this baseline is explicitly out of
scope -- this benchmark's job is only to capture the number before anyone
touches performance. Benchmarking the other endpoints, a concurrent/
load-test variant, or the end-to-end job-completion latency (creation
through a terminal status) are all different, undefined measurements a
future task could add; this one fixes the single-endpoint, sequential
baseline only.
