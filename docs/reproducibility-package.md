# Reproducibility Package — LOCKED

This document records the reproducibility package. It is
not a brainstorming document. Every command below is either copied
from its own locked source doc or was run for real during this
project's own test passes (`docs/clean-start-test.md`,
`docs/end-to-end-test-pass.md`) — nothing here is untested.

## 1. Clean setup

```bash
git clone <this repo>
cd AI-Earth-intelligence-and-Forecasting-Engine
cp .env.example .env        # fill in FIRMS_MAP_KEY at minimum;
                             # GEMINI_API_KEY needed for planner/ask-earth
uv sync --project ml        # Python 3.12+, installs ml/ as an
                             # editable package (docs/clean-start-test.md
                             # fixed the real gap where this used to
                             # silently install nothing)
```

## 2. Local services

```bash
cd infra/docker
docker compose up -d --build
curl http://localhost:8080/readyz   # {"status":"UP"}
```

Brings up Postgres/PostGIS, Redis, MinIO, Jaeger, the backend
(`:8080`), and the frontend (`:5173`) — five containers, verified from
a genuinely clean build in `docs/clean-start-test.md`. For local Java
development against the same infra without rebuilding the backend
image each time:

```bash
docker compose up -d postgres redis minio jaeger   # infra only
cd backend && ./mvnw spring-boot:run
cd frontend && npm run dev                          # :5173, Vite
```

## 3. Earth analysis

A real, live natural-language request (the exact request `client.ts`
itself sends):

```bash
curl -X POST http://localhost:8080/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "How many wildfires occurred in the Bay Area during August 2024?"}'
# -> {"id": "...", "status": "SUCCEEDED"}

curl http://localhost:8080/queries/<id>/result
```

A real run of exactly this (`docs/end-to-end-test-pass.md`) returned:

```json
{
  "answer": "There were 245 wildfires in the Bay Area during August 2024 (computed).",
  "facts": [{"result": {"count": 245}, "evidence": {"dataset": "NASA_FIRMS:VIIRS_SNPP_SP", "region_label": "bay_area", "period_start": "2024-08-01T00:00:00+00:00", "period_end": "2024-09-01T00:00:00+00:00"}}]
}
```

The structured, non-LLM equivalent (no planner call, one fixed
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

curl http://localhost:8080/forecasts/<forecast_id>          # poll until terminal
curl http://localhost:8080/forecasts/<forecast_id>/result
```

**Requires a real trained production model first** — `ml/artifacts/production_model_v1/`
is a gitignored local build artifact, not stored in the repo. The backend
image copies it in at build time, so build it before `docker compose
build` and before expecting `SUCCEEDED` (section 5 below, first two
commands). Without it, `POST /forecasts` reaches a
real, honest `FAILED`/`422` naming the missing model
(`docs/clean-start-test.md`) rather than a silent or fabricated result.

Use an **on-grid weekly cutoff** (10:00 UTC, every 7 days from June 1
through October — `build_historical_dataset.py`'s own cutoff rule,
e.g. `2024-08-10T10:00:00Z` above) for an exact ERA5/FIRMS alignment;
an off-grid cutoff still runs, falling back to the latest cutoff before
it (`ERA5History.for_cutoff`'s documented contract).

A real run of exactly this (`docs/end-to-end-test-pass.md`) reached
`SUCCEEDED` with 9,975 real grid cells, model version `v1`, a real
2-bin calibration table, and full evidence.

## 5. ML benchmark

```bash
python scripts/forecast/build_historical_dataset.py   # once; needs
                                                        # data/raw/{firms,era5,geography}
                                                        # history already ingested
python scripts/models/train_production_model.py       # writes
                                                        # ml/artifacts/production_model_v1/
                                                        # -- needed for section 4 above

python scripts/models/run_ml_benchmark.py        # PR-AUC/ROC-AUC/Brier/
                                                        # log loss/inference time,
                                                        # all four locked models
python scripts/models/run_ablation_benchmark.py  # fire history vs
                                                        # +weather vs
                                                        # +weather+geography
```

Real results from these exact commands: `docs/ml-benchmark.md`,
`docs/ablation-benchmark.md`.

## 6. Distributed benchmark

```bash
python scripts/distributed/run_scaling_benchmark.py       # 1/2/4/8 workers:
                                                            # runtime, throughput,
                                                            # speedup, efficiency
python scripts/distributed/run_fault_injection_test.py    # a real killed worker:
                                                            # detection + recovery
```

Uses the small, frozen 500-tile sample workload
(`distributed/workload.py`) — no historical dataset build needed for
this one. Real results from these exact commands:
`docs/distributed-benchmark.md`.

## What this package does not cover

**The AI planner benchmark** (`python scripts/query/run_planner_benchmark.py`,
needs `GEMINI_API_KEY`) is real and reproducible but calls a live,
unseeded LLM — README's "How to reproduce" and
`docs/planner-accuracy-benchmark.md` cover it; it is left out of this
numbered package because re-running it does not reproduce the same
exact numbers the way every command above does (documented directly in
`docs/planner-accuracy-benchmark.md`'s own run-to-run comparison).
**Cloud/Kubernetes deployment** commands are in `docs/local-kubernetes-deployment.md`
and `docs/cloud-deployment.md` — out of scope for a local
reproducibility package (and, per README's Deployment section, the
cloud path was never applied to a real AWS account).
