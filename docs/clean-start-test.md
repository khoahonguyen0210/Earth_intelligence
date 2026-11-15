# Clean-Start Test

This test checks that the stack in `docs/docker-compose-stack.md` builds
and runs from a clean state, not only that its files look correct.

## Commands

```bash
cd infra/docker
docker compose up -d --build
curl http://localhost:8080/actuator/health
curl -X POST http://localhost:8080/analyses -H "Content-Type: application/json" -d '{...}'
curl http://localhost:8080/results/{id}
curl -X POST http://localhost:8080/forecasts -H "Content-Type: application/json" -d '{...}'
curl http://localhost:8080/forecasts/{forecast_id}
curl -X POST http://localhost:8080/forecasts/{forecast_id}/result
```

The public health check later moved to `/readyz`. Full actuator health
is now on the internal management port (see `docs/security-baseline.md`).

## Bugs found

A clean build has no leftover installs and no shell variables set by
hand. It exposed two bugs that a working developer machine had hidden.

**1. `uv sync` did not install the local package.** `ml/pyproject.toml`
had no `[build-system]` table, so `uv.lock` recorded the project as
`source = { virtual = "." }`: dependencies only, never the package
itself. The scripts under `scripts/` still worked on the developer
machine because an older manual `pip install -e .` had left an editable
install in the shared `.venv`. In the container, `uv sync --frozen`
installed only what the lock file described, and the first analysis
request failed with `ModuleNotFoundError: No module named
'ai_earth_intelligence_and_forecasting_engine'`.

The fix adds a `[build-system]` table and `[tool.uv] package = true` to
`ml/pyproject.toml` and regenerates `uv.lock`, which now records
`source = { editable = "." }`. The fix is in the project configuration,
so any clean `uv sync` works, inside a container or not.

**2. `FIRMS_MAP_KEY` did not reach the container.** `data.firms`
requires the NASA FIRMS key even when a request only reads the local
sample CSV. On the developer machine the key was always set. In the new
container nothing set it, and the same request failed with
`FIRMS_MAP_KEY is not configured`. The fix adds `env_file: ../../.env`
to the backend service (see `docs/docker-compose-stack.md`). This is the
same git-ignored `.env` file that the scripts read.

## Result

```text
[x] docker compose up -d --build   all five containers start; the backend
                                   waits for the postgres, redis and minio
                                   health checks
[x] GET /actuator/health           {"status":"UP"}, db and redis both UP
[x] GET http://localhost:5173/     200, the Vite build served by nginx
[x] POST /analyses -> GET /results/{id}
                                   the Earth analysis succeeds:
                                   {"result":{"count":198}, "evidence": {...}}
                                   for "how many fires occurred in California
                                   between 2024-08-01 and 2024-08-20"
[ ] POST /forecasts -> GET /forecasts/{id}/result
                                   ends in FAILED with a known data error,
                                   not a Docker bug (see below)
```

## Why the forecast request failed

At the time of this test, `compute_forecast` trained a model on the fly
at two fixed demo cutoffs, `TRAIN_DEMO_CUTOFF` and
`VALIDATION_DEMO_CUTOFF` (2020-08-15 and 2023-08-15, in
`query.run_forecast`). The small FIRMS sample file has no fire in either
cutoff's lookback window for any region. `fit_xgboost` refuses to fit
when the training split has only one class, so it returned a clear
error instead of a made-up result. `ForecastWorker` then moved the job
to `FAILED` and kept the message, which is the designed behavior for a
permanent failure. The failure was the same with or without Docker.

Forecasts now load the trained production model
(`load_production_model` in `query.run_forecast`), so this failure no
longer applies.

## Outcome

The goal was that the full local product starts from documented
commands, the same way every time. It does: five containers, passing
health checks, and a working Earth analysis.
