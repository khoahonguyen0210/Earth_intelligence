# Clean-Start Test — LOCKED

This document freezes the clean-start test. It is not a
brainstorming document. It verifies `docs/docker-compose-stack.md`
actually works, from a genuinely clean build -- not just
that the compose file and Dockerfiles look correct on paper.

## The commands

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

## Two real bugs this test caught, neither hypothetical

A clean container build exercises two things a working local machine
already papers over: a from-scratch `uv sync` (no leftover manual
install lying around), and a from-scratch environment (no ambient shell
variables a developer set once and forgot about). Both surfaced real
failures here.

**1. The local package was never actually installed by `uv sync`.**
`ml/pyproject.toml` had no `[build-system]` table, so `uv.lock` recorded
the root project as `source = { virtual = "." }` -- dependencies-only,
never built or installed. Every real caller under `scripts/` still
imported the package fine on a real local machine only because *some*
earlier, `uv`-independent command (a manual `pip install -e .` or
equivalent, lost to history) had left a real editable install sitting
in that machine's shared `.venv`, invisible to and unreproduced by
`uv sync` itself. Inside a genuinely clean container, `uv sync --frozen`
reproduced only what the lockfile actually described -- nothing --
and the very first live analysis request failed with
`ModuleNotFoundError: No module named
'ai_earth_intelligence_and_forecasting_engine'`. Fixed by adding a real
`[build-system]` table and `[tool.uv] package = true` to
`ml/pyproject.toml`, then regenerating `uv.lock` (now
`source = { editable = "." }`) -- a real fix to the project's own
dependency configuration, not a Dockerfile workaround, since the same
gap would have bitten any other genuinely clean `uv sync`, container or
not.

**2. `FIRMS_MAP_KEY` never reached the container.** `data.firms`
requires this real NASA FIRMS credential unconditionally,
even for a request that only reads the local sample CSV. Locally it is
always present because every developer's shell/`.env` already has it;
inside a fresh container, nothing set it, and the very same analysis
request failed with `FIRMS_MAP_KEY is not configured`. Fixed by adding
`env_file: ../../.env` to the backend service (`docs/docker-
compose-stack.md`), the same real, gitignored local `.env` every
`scripts/*.py` real-caller already reads.

Both are exactly what a clean-start test is supposed to find: gaps that
years of "it works on my machine" hide, that a genuinely fresh
environment cannot.

## Result

A real run against the fixed stack:

```text
[x] docker compose up -d --build  -- all five containers start; backend
    waits on postgres/redis/minio's healthchecks before starting itself
[x] GET /actuator/health          -- {"status":"UP"}, db/redis both UP
[x] GET http://localhost:5173/    -- 200, the real Vite build served by
    nginx
[x] POST /analyses -> GET /results/{id} -- a real Earth analysis
    succeeds: {"result":{"count":198}, "evidence": {...}} for "how many
    fires occurred in California between 2024-08-01 and 2024-08-20"
[ ] POST /forecasts -> GET /forecasts/{id}/result -- reaches FAILED
    with a real, pre-existing, already-documented error, not a Docker
    bug (see below)
```

## The forecast request's real failure is not this task's to fix

`compute_forecast`'s fixed `TRAIN_DEMO_CUTOFF`/`VALIDATION_DEMO_CUTOFF`
(2020-08-15 / 2023-08-15, `query.run_forecast`) build training rows from
the same small real FIRMS sample file every other real caller in this
project already uses -- and that sample simply has no real fire
observation landing in either fixed cutoff's lookback window, for any
region. `fit_xgboost` correctly refuses to fit on a single-class
training split (the exact same real, structural data-availability gap
`models/profiling.py`'s `synthetic_timing_rows` fallback already
exists to work around for *computational* benchmarks) and
returns a clear, real error rather than a fabricated result --
`ForecastWorker` correctly propagates that to a
`FAILED` terminal state with the real message intact, exactly as
permanent failures were designed to behave. This is present and
identical whether the backend runs locally or in this container; this
packaging task's job was to package and run what already exists, not to give the
locked forecasting dataset more real historical fire coverage
at these two fixed dates.

## What "done" means here

The bar for this task: "the complete local product
starts reproducibly from documented commands." It does -- five
containers, real health checks, and a real Earth-analysis result,
reproducibly, from the commands above. A forecast request against this
particular small sample dataset at these particular fixed demo cutoffs
correctly fails for a real, pre-existing, already-understood reason;
demonstrating a real successful forecast end to end would need
different sample data or different demo cutoffs, both decisions made
elsewhere, not something this packaging task is scoped to change.
