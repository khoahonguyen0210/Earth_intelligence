# Reproducibility Package

Every command below is copied from the document that defines it, or was
run during the project's test passes (`docs/clean-start-test.md`,
`docs/end-to-end-test-pass.md`, `docs/clean-clone-test.md`). Nothing
here is untested.

## 1. Setup

```bash
git clone <this repo>
cd AI-Earth-intelligence-and-Forecasting-Engine
cp .env.example .env        # fill in FIRMS_MAP_KEY at least;
                            # GEMINI_API_KEY is needed for the planner and Ask Earth
uv sync --project ml        # Python 3.12+, installs ml/ as an
                            # editable package (docs/clean-start-test.md
                            # fixed the bug where this installed nothing)
```

## 2. Local services

```bash
cd infra/docker
docker compose up -d --build
curl http://localhost:8080/readyz   # {"status":"UP"}
```

This starts Postgres/PostGIS, Redis, MinIO, Jaeger, the backend
(`:8080`) and the frontend (`:5173`): six containers, checked from a
clean clone in `docs/clean-clone-test.md`. For Java development against
the same services without rebuilding the backend image each time:

```bash
docker compose up -d postgres redis minio jaeger   # services only
cd backend && ./mvnw spring-boot:run
cd frontend && npm run dev                          # :5173, Vite
```

## 3. Earth analysis

A live request in plain English (the same request that `client.ts`
sends):

```bash
curl -X POST http://localhost:8080/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "How many wildfires occurred in the Bay Area during August 2024?"}'
# -> {"id": "...", "status": "SUCCEEDED"}

curl http://localhost:8080/queries/<id>/result
```

A run of this request (`docs/end-to-end-test-pass.md`) returned:

```json
{
  "answer": "There were 245 wildfires in the Bay Area during August 2024 (computed).",
  "facts": [{"result": {"count": 245}, "evidence": {"dataset": "NASA_FIRMS:VIIRS_SNPP_SP", "region_label": "bay_area", "period_start": "2024-08-01T00:00:00+00:00", "period_end": "2024-09-01T00:00:00+00:00"}}]
}
```

The structured version, without the LLM (no planner call, one fixed
operation):

```bash
curl -X POST http://localhost:8080/analyses \
  -H "Content-Type: application/json" \
  -d '{"question": "How many fires occurred in California between 2024-08-01 and 2024-08-20?", "intent": "count", "region": {"kind": "named", "value": "california"}, "time_range": {"start": "2024-08-01", "end": "2024-08-20"}, "operation": "count"}'
curl http://localhost:8080/results/<id>
```

## 4. Forecast

```bash
curl -X POST http://localhost:8080/forecasts \
  -H "Content-Type: application/json" \
  -d '{"region": {"kind": "named", "value": "california"}, "cutoff": "2024-08-10T10:00:00Z"}'
# -> {"forecast_id": "...", "status": "PENDING"}

curl http://localhost:8080/forecasts/<forecast_id>          # poll until it finishes
curl http://localhost:8080/forecasts/<forecast_id>/result
```

**This needs a trained production model first.**
`ml/artifacts/production_model_v1/` is a local build output that git
ignores; it is not in the repository. The backend image copies it at
build time, so build it before `docker compose build` and before
expecting `SUCCEEDED` (the first two commands in section 5). Without
it, `POST /forecasts` ends in `FAILED`/`422` with a message naming the
missing model (`docs/clean-start-test.md`), not an empty or invented
result.

Use a weekly cutoff on the grid (10:00 UTC, every 7 days from June 1
through October, the cutoff rule of `build_historical_dataset.py`, for
example `2024-08-10T10:00:00Z` above) so that ERA5 and FIRMS line up
exactly. A cutoff off the grid still runs, using the latest cutoff
before it (the documented behavior of `ERA5History.for_cutoff`).

A run of this request (`docs/end-to-end-test-pass.md`) reached
`SUCCEEDED` with 9,975 grid cells, model version `v1`, a 2-bin
calibration table and full evidence.

## 5. ML benchmark

```bash
python scripts/forecast/build_historical_dataset.py   # once; needs the
                                                      # data/raw/{firms,era5,geography}
                                                      # history downloaded first
python scripts/models/train_production_model.py       # writes
                                                      # ml/artifacts/production_model_v1/,
                                                      # needed for section 4

python scripts/models/run_ml_benchmark.py             # PR-AUC, ROC-AUC, Brier,
                                                      # log loss and inference
                                                      # time for all four models
python scripts/models/run_ablation_benchmark.py       # fire history vs
                                                      # +weather vs
                                                      # +weather+geography
```

Results from these commands: `docs/ml-benchmark.md` and
`docs/ablation-benchmark.md`.

## 6. Distributed benchmark

```bash
python scripts/distributed/run_scaling_benchmark.py       # 1/2/4/8 workers:
                                                          # runtime, throughput,
                                                          # speedup, efficiency
python scripts/distributed/run_fault_injection_test.py    # a killed worker:
                                                          # detection and recovery
```

These use the small, frozen 500-tile sample workload
(`distributed/workload.py`), so they need no historical dataset.
Results from these commands: `docs/distributed-benchmark.md`.

## Not covered

**The AI planner benchmark**
(`python scripts/query/run_planner_benchmark.py`, needs
`GEMINI_API_KEY`) can be run again, but it calls a live LLM with no
fixed seed, so it does not give exactly the same numbers each time
(see the comparison between runs in
`docs/planner-accuracy-benchmark.md`). The README's "How to reproduce"
section and that document cover it.

**Kubernetes and cloud deployment** commands are in
`docs/local-kubernetes-deployment.md` and `docs/cloud-deployment.md`.
They are outside a local reproducibility package, and, as the README's
Deployment section says, the cloud setup was never applied to an AWS
account.
