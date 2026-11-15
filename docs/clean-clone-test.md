# Final Clean-Clone Test

This is the final check of the implementation. It runs the full chain
from a new clone: clone -> install -> configure -> tests -> local stack
-> Earth analysis -> forecast -> reproduce one benchmark. Every step
below was run, not simulated.

## Setup: a separate clone

```bash
git clone -b <branch> <this repo> C:/aiearth-cct
```

Data that git ignores and the repository cannot ship (the raw FIRMS,
ERA5 and geography history, the built `historical_dataset_v1.csv` and
the trained `production_model_v1`) was copied from the working copy.
It was not downloaded again or rebuilt. `.env` was copied the same way.
The goal is to prove that the code and packaging work from a clean
checkout, not to repeat data downloads that take hours and have nothing
to do with this check.

## Bugs found

This run found two documentation bugs. Both were fixed in the same
commit.

1. **`/actuator/health` returns 404 on the public port.** Older docs
   (`docs/clean-start-test.md`, `README.md` and
   `docs/reproducibility-package.md`) gave
   `curl http://localhost:8080/actuator/health` as the health check.
   That was correct when the clean-start test ran. Later, the security
   work moved full actuator health to an internal management port and
   added a status-only `/readyz` on the public port, and no one checked
   the old command again. `README.md` and
   `docs/reproducibility-package.md` now use
   `curl http://localhost:8080/readyz`. `docs/clean-start-test.md`
   keeps the commands that ran at the time, with a note about the
   change.
2. **The documented `/analyses` request body was missing required
   fields.** The example in `docs/reproducibility-package.md` left out
   `question` and `intent`, which are both `@NotBlank` in
   `AnalysisRequest`. Running the command, instead of only reading the
   Java code, showed the error. The working request body is now in
   that document.

A stale local kind Kubernetes cluster (`ai-earth-control-plane`, left
over from the Kubernetes deployment work) was also holding host ports
8080 and 5173 through its port forwarding. `docs/ask-earth.md` had run
into the same conflict once. It was removed with `docker rm -f`.

## Steps and results

```text
[x] clone       git clone -b <branch>, no file-name-length or checkout
                errors once the destination path was short enough for
                Windows MAX_PATH (a local limit, not a project bug;
                `git -c core.longpaths=true` also works with a long
                destination path)
[x] install     uv sync --project ml (new venv, all dependencies
                installed); ./mvnw package -DskipTests (BUILD SUCCESS,
                54.9s); npm install (236 packages, 0 vulnerabilities)
[x] configure   .env copied in (FIRMS_MAP_KEY, GEMINI_API_KEY,
                CDSAPI_KEY)
[x] tests       backend 173 passed, ml 539 passed (0 skipped), frontend
                49 passed; 761 in total, 0 failures, all fresh
[x] local stack docker compose up -d --build: all 6 containers healthy
                on their documented ports (8080, 5173, 5432, 6379,
                9000-9001, 4318/16686) after the stale kind cluster
                was removed
[x] Earth       POST /analyses -> GET /results/{id}: a count
    analysis    (5,814 fires, California, 2024-08-01 to 2024-08-20)
                with full evidence
[x] forecast    POST /forecasts -> GET /forecasts/{id}/result: a
                SUCCEEDED prediction with the copied production
                model; 9,975 grid cells, model version v1
[x] reproduce   scripts/distributed/run_scaling_benchmark.py: the same
    one         pattern as docs/distributed-benchmark.md, slower with
    benchmark   each added worker (1 worker 0.879s, 8 workers 18.7s)
```

## Outcome

All eight steps ran in a folder the project had never used before, and
the run found two documentation bugs, which is what a final check is
for. Both are fixed. The clone (`C:/aiearth-cct`) was deleted after the
run.
