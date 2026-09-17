# Final Clean-Clone Test — LOCKED

This document records the final clean-clone test,
the handbook's own final implementation gate. It is not a
brainstorming document.

The full chain, run for real from a genuinely fresh clone: clone ->
install -> configure -> tests -> local stack -> Earth analysis ->
forecast -> reproduce one benchmark. Every step below was actually run,
not simulated.

## Setup: a genuinely separate clone

```bash
git clone -b <branch> <this repo> C:/aiearth-cct
```

Real, gitignored data this repo cannot ship (raw FIRMS/ERA5/geography
history, the built `historical_dataset_v1.csv`, the trained
`production_model_v1`) was copied in from the working repo rather than
re-fetched from external APIs or rebuilt from scratch for this run --
real data already paid for and validated earlier in this project, not
re-downloaded or fabricated. `.env` was copied the same way. This
matches the choice already made and documented for this task: prove
the *code and packaging* work from a truly clean checkout, not
re-derive multi-hour external data pulls that have nothing to do with
this gate.

## Two real bugs this gate caught

A gate is only as good as what it actually catches. This run found two
genuine, current documentation bugs -- both fixed in this same commit:

1. **`/actuator/health` 404s on the public port.** Every earlier doc
   (`docs/clean-start-test.md`, and this project's own `README.md` and
   `docs/reproducibility-package.md` before this fix) documented
   `curl http://localhost:8080/actuator/health` as the health check.
   That was correct when the clean-start test was written -- the security
   baseline work later moved full actuator health to an internal-only
   management port and put a status-only `/readyz` on the public one,
   and nothing had re-checked the older doc's command since. Fixed
   `README.md` and `docs/reproducibility-package.md` to `curl
   http://localhost:8080/readyz`; `docs/clean-start-test.md` itself is
   left as the historical record of what actually ran at the time, not
   rewritten.
2. **The documented `/analyses` request body was missing required
   fields.** `docs/reproducibility-package.md`'s own example (written
   earlier in this same phase) omitted `question` and `intent`, both
   `@NotBlank`-required on the real `AnalysisRequest` -- caught the
   moment this gate actually ran the command instead of only reading
   the Java source. Fixed with the real, working request body below.

Also cleaned up along the way: a stale local `kind` Kubernetes cluster
(`ai-earth-control-plane`, leftover from earlier Kubernetes-deployment
work) had been squatting on host ports 8080 and 5173 via its own
port-forwarding this whole time -- the same recurring conflict
`docs/ask-earth.md` already ran into once. Removed for
real (`docker rm -f`), confirmed with the project owner first since it
was pre-existing infrastructure, not something this session created.

## The result, step by step

```text
[x] clone       git clone -b <branch>, no filename-length or checkout
                 errors once the destination path was short enough for
                 Windows MAX_PATH (a real local constraint, not a
                 project bug -- `git -c core.longpaths=true` also works
                 without a long destination path)
[x] install     uv sync --project ml (fresh venv, all deps installed
                 clean); ./mvnw package -DskipTests (BUILD SUCCESS,
                 54.9s); npm install (236 packages, 0 vulnerabilities)
[x] configure   .env copied in (real FIRMS_MAP_KEY/GEMINI_API_KEY/
                 CDSAPI_KEY)
[x] tests       backend 173 passed, ml 539 passed (0 skipped), frontend
                 49 passed -- 761 total, 0 failures, all fresh
[x] local stack docker compose up -d --build: all 6 containers healthy
                 on their documented ports (8080, 5173, 5432, 6379,
                 9000-9001, 4318/16686) once the stale kind cluster was
                 cleared
[x] Earth       POST /analyses -> GET /results/{id}: a real count
    analysis    (5,814 fires, California, 2024-08-01 to 2024-08-20)
                 with full evidence
[x] forecast    POST /forecasts -> GET /forecasts/{id}/result: a real
                 SUCCEEDED prediction using the copied production
                 model -- 9,975 grid cells, model version v1
[x] reproduce   scripts/distributed/run_scaling_benchmark.py: the same
    one         monotonically-slower-with-more-workers pattern as
    benchmark   docs/distributed-benchmark.md (1 worker 0.879s,
                 8 workers 18.7s) -- reproduced, not just repeated
```

## What "done" means here

Every one of the handbook's eight steps ran for real, against a
directory this project had never touched before, and found two real
documentation bugs in the process -- exactly what a final gate is for.
Both are fixed. The clone itself (`C:/aiearth-cct`) was deleted after
this run; nothing about it persists beyond this record and the fixes
it produced.
