# AI Earth Intelligence & Forecasting Engine

A web-based Earth intelligence platform: a user asks a natural-language
question about Earth, and the system identifies the geographic and
temporal scope, retrieves the required Earth data, executes a
validated analysis workflow, and returns an evidence-backed answer —
never a fabricated one. Forecasting is one capability used to validate
the platform's scientific and computational depth, not the whole
product.

## What it is

Ask a question like "How many wildfires occurred in the Bay Area
during August 2024?" or "What's the wildfire risk for California
starting tomorrow?" and the system:

1. Sends the question to an LLM planner, which produces a structured,
   typed plan (never free-form code).
2. Runs that plan through a deterministic validator before anything
   executes — the LLM chooses tools, it never bypasses this gate or
   runs arbitrary logic.
3. Executes the validated plan against real Earth data (fire history,
   weather, geography) and a real trained forecasting model.
4. Returns an answer with its evidence attached: dataset, time range,
   region, model version, and calibration — so every number is
   traceable back to what actually produced it.

## Problem

The first flagship capability is a locked scientific problem:
**24-hour wildfire occurrence-risk forecasting on a fixed California
0.1° grid**, using public Earth-observation, weather, and geographic
data.

For each grid cell `G` at hourly cutoff `T`:

```text
target = 1 if at least one qualifying NASA FIRMS active-fire
           observation occurs in G during the next 24 hours
target = 0 otherwise
```

A feature may only use information available at or before its own
cutoff — enforced by a dedicated, consolidated leakage-safety test
suite (`ml/tests/forecast/test_leakage.py`), not just by convention.
The historical split is fixed and never reopened after configuration
is frozen:

```text
TRAIN       2019-01-01 -> 2022-12-31
VALIDATION  2023-01-01 -> 2023-12-31
TEST        2024-01-01 -> 2024-12-31   (held out until config is frozen)
```

## Product

- **Earth Intelligence**: event counts, recent activity, change
  between two periods, spatial aggregation, time-series summaries, map
  results — all through the same natural-language pipeline.
- **Wildfire forecasting**: a near-term risk request returns
  probability/risk, a map, the forecast window, the data cutoff, the
  model version, a calibration table, and evidence — submitted as an
  async job with real queued/running/completed/failed status, not a
  blocking call.
- **Natural-language orchestration**: the LLM interprets intent,
  extracts geography/time, chooses from a fixed tool surface, and
  explains the executed result. It is explicitly not the scientific
  calculator — every number it reports was computed by deterministic
  code, not generated.
- **Evidence, always**: every result carries its source/dataset,
  period, geographic scope, processing/model version, and workflow
  provenance.

## Results

Selected, real, measured, reproducible results
(`docs/headline-results.md`; full detail in each linked doc):

> **Achieved a PR-AUC of 0.4513 with XGBoost — nearly double
> climatology's 0.2522 baseline — by training the locked feature set
> on the real 2019-2022 California fire history and weather record
> (877,800 rows, 88 weekly cutoffs).**
> `docs/final-ml-benchmark.md`

> **Achieved a PR-AUC gain of +0.081 (0.370 -> 0.451) by adding real
> terrain and land-cover features — elevation, slope, ESA WorldCover
> class — on top of fire history and weather, more than five times
> weather's own +0.014 contribution.**
> `docs/final-ablation-benchmark.md`

> **Achieved well-calibrated probabilities — predicted and observed
> fire frequency matching to three decimal places across the dominant
> bin (218,223 of 219,450 real test rows) — by isotonic-calibrating
> XGBoost on the validation split before evaluating on the held-out
> test split.**
> `docs/final-ml-benchmark.md`

> **Achieved zero lost tiles after a real killed worker — recovered in
> 1.353 seconds — by detecting the failure via a per-chunk timeout and
> retrying only the lost chunk against the same worker pool.**
> `docs/final-distributed-benchmark.md`

> **Achieved 100% intent correctness, 100% region correctness, and
> 100% execution success across 14 real natural-language questions
> against the live Gemini API, by validating every planner-produced
> plan against the real backend tool schema before any step executes.**
> `docs/final-planner-benchmark.md`

Real findings that did **not** clear the bar for a headline (mixed
effect sizes, platform limitations, run-to-run LLM variance) are listed
honestly in `docs/headline-results.md` rather than omitted.

## Architecture

```text
React + TypeScript
      |
Java 21 / Spring Boot
      |
   +--+-----------------+
   |                     |
sync analysis       async jobs
   |                     |
   |                   Redis
   |                     |
   |               Python workers
   |                     |
   +----------> PostGIS / Object Storage
                         |
                   Earth Data Sources
```

Natural-language requests additionally pass through:

```text
question -> LLM planner -> structured plan -> deterministic validator
         -> workflow -> Redis/workers -> scientific computation
         -> evidence-backed result
```

The Java backend never runs Python inline; it spawns a real Python
subprocess per request (analysis/forecast/ask-earth), communicating
over stdin/stdout JSON, with a bounded timeout and threaded
stdout/stderr draining. Async forecast jobs are queued in Redis and
picked up by a worker loop inside the same backend process; a
scheduled recovery sweep (`ForecastRecovery`) re-claims any job left
`RUNNING` past its timeout, so a crashed worker never silently loses a
job (verified with a real killed process — see Results above).

## Data

| Source | Provides | Access |
|---|---|---|
| NASA FIRMS | historical active-fire detections | public API |
| ERA5-Land (Copernicus CDS) | 2m temperature, precipitation, 10m wind, humidity | CDS API |
| Copernicus DEM GLO-30 | elevation, slope | public AWS Open Data S3 |
| ESA WorldCover 10m v200 | land-cover class | public AWS Open Data S3 |

The real historical training dataset (`data/processed/historical_dataset_v1.csv`,
1,316,700 rows) is built once by `scripts/forecast/build_historical_dataset.py`
from real, ingested history for all four sources — not sample data.
None of the four providers' contract docs (`docs/firms-input-contract.md`,
`docs/era5-land-input-contract.md`, `docs/static-geography-input-contract.md`)
state explicit license terms; check each provider's current terms
before reuse beyond this project's own research use.

## Scientific method

- **Locked feature groups**: fire history (previous 24h/72h/7d/30d
  counts, neighboring-cell 24h count), weather (temperature,
  precipitation, wind u/v, relative humidity), static geography
  (elevation, slope, land-cover class) — no arbitrary feature
  expansion beyond these.
- **Locked model ladder**: Climatology baseline -> Logistic Regression
  -> XGBoost -> Calibrated XGBoost (isotonic). No neural model in the
  main benchmark.
- **Metrics**: PR-AUC, ROC-AUC, Brier score, log loss, calibration
  curve (primary); training/inference time, artifact size (secondary).
  Accuracy is deliberately not used — wrong metric for this class
  imbalance (~0.45% positive rate).
- **Leakage safety**: a dedicated, consolidated test suite proves
  every feature/target/split property that could otherwise leak future
  information (`ml/tests/forecast/test_leakage.py`,
  `docs/scientific-regression-tests.md`).
- **Reproducibility**: every trained model artifact carries its own
  `metadata.json` — dataset/feature version, split summaries, the
  fixed random seed actually used, and pinned library versions;
  loading refuses a library-version mismatch rather than risk silently
  different predictions (`ml/src/.../models/production_model.py`,
  proven deterministic by `ml/tests/models/test_production_model.py`).

## How to run

Local, Docker Compose, from a clean clone:

```bash
cp .env.example .env        # fill in FIRMS_MAP_KEY at minimum
cd infra/docker
docker compose up -d --build
curl http://localhost:8080/readyz
```

Brings up Postgres/PostGIS, Redis, MinIO, Jaeger, the backend
(`:8080`), and the frontend (`:5173`) — five containers, no reverse
proxy; the browser talks to the backend directly. Verified end to end
in `docs/clean-start-test.md`.

For local development instead of the packaged images: `cd frontend &&
npm run dev` (Vite, port 5173) and `cd backend && ./mvnw spring-boot:run`
against the same `docker compose` Postgres/Redis/MinIO.

## How to reproduce

Python environment (`ml/`, uv-managed, Python >= 3.12):

```bash
uv sync --project ml
```

Build the real dataset and the production model (once; each takes
real time and real ingested history under `data/raw/`):

```bash
python scripts/forecast/build_historical_dataset.py
python scripts/models/train_production_model.py
```

Run each of the four final Phase 16 benchmarks:

```bash
python scripts/models/run_final_ml_benchmark.py          # PR-AUC/ROC-AUC/Brier/log loss/calibration
python scripts/models/run_final_ablation_benchmark.py    # fire history vs +weather vs +weather+geography
python scripts/distributed/run_scaling_benchmark.py      # 1/2/4/8-worker runtime/throughput/speedup
python scripts/query/run_planner_benchmark.py            # needs GEMINI_API_KEY in .env
```

Each prints a summary table and writes its raw result under
`ml/artifacts/` or `data/processed/` (both gitignored, regenerable).
Re-running the planner benchmark calls a real, unseeded LLM — expect
the exact plan wording, and possibly a metric or two, to vary run to
run (documented directly in `docs/final-planner-benchmark.md`).

## Testing

```bash
cd backend && ./mvnw test          # needs docker compose up -d first
uv run --project ml pytest ml/tests -q   # from repo root
cd frontend && npm test            # PowerShell on Windows, not Git Bash
```

Last full pass: ml 539 passed / 0 skipped, backend 173 passed,
frontend 49 passed (`docs/scientific-regression-tests.md`,
`docs/unit-test-pass.md`) — 761 tests total, real infrastructure
throughout (this codebase has no mocked-datasource tier; every backend
test boots against a real Postgres/Redis/MinIO). End-to-end and
reliability evidence (earth analysis, forecast, worker crash,
duplicate request) is in `docs/end-to-end-test-pass.md` and
`docs/reliability-tests.md`. CI (`.github/workflows/ci.yml`) runs
Python, Java, frontend, and a dependency/secret security scan as four
parallel jobs.

## Deployment

- **Docker**: two images — `backend/Dockerfile` (Java 21 JRE plus a
  bundled Python venv; the Java-to-Python bridge is an in-process
  subprocess, not a network call) and `frontend/Dockerfile` (nginx
  serving the built Vite app). `docs/docker-images.md`.
- **Kubernetes**: 7 manifests under `infra/k8s/`, verified against a
  local `kind` cluster — health, job execution, service connectivity,
  and pod-restart recovery all confirmed live. `docs/kubernetes-manifests.md`,
  `docs/local-kubernetes-deployment.md`.
- **Cloud (AWS)**: Terraform for EKS, RDS PostgreSQL/PostGIS,
  ElastiCache Redis, S3, Secrets Manager, and an ALB, across
  `infra/terraform/modules/`. **Written and validated
  (`terraform fmt`/`validate` pass, Trivy clean), never applied** —
  the project owner chose not to incur real AWS cost for a demo
  deployment. No domain was purchased, so the design serves HTTP on
  the ALB's own AWS DNS name rather than HTTPS on a custom domain;
  HTTPS config exists but is not enabled. `docs/cloud-deployment.md`,
  `docs/terraform-layout.md`.

## Limitations

Reported the same way every result above is — real and specific, not
hedged:

- **No redelivery/visibility-timeout protocol on the Redis queue
  itself.** Recovery works entirely off the database's own
  `updated_at` column, not broker-level redelivery.
- **No cancel endpoint** for a submitted forecast or analysis job.
- **The malformed-Earth-data reliability scenario covers the analysis
  pipeline only, not the full forecast pipeline** — a forecast-pipeline
  version needs a fixture this project's sample data can't support
  (`docs/reliability-tests.md`).
- **Weather features contribute little on top of fire history alone**
  at this feature set and data volume (+0.014 PR-AUC, -0.012 ROC-AUC)
  — a real, measured, mixed finding, not a bug.
- **More distributed workers made the benchmark workload slower, not
  faster, on this project's Windows/`multiprocessing.spawn` platform**
  — process-spawn overhead dominates a workload this small; a
  fork-based Linux target or a persistent worker pool is unexplored.
- **The planner sometimes answers an unanswerable causal question**
  ("why does California have so many wildfires") with an adjacent
  count plan instead of rejecting it — a real, reproduced limitation,
  not a validator gap (the produced plan is structurally valid).
- **Cloud deployment was never applied to a real AWS account** — the
  Terraform is validated but unexercised; no real cloud runtime or
  cost numbers exist, only the estimate in `docs/cloud-deployment.md`.
- **No HTTPS/custom domain** — internal/demo deployment only, by the
  project owner's own choice.

## Reuse/attribution

MIT licensed (see `LICENSE`).

Reused, unmodified third-party infrastructure (Apache-2.0), recorded
per this project's own reuse policy:

| Module | Version | License | Used as |
|---|---|---|---|
| `terraform-aws-modules/vpc/aws` | 6.7.3 | Apache-2.0 | `infra/terraform/modules/network` |
| `terraform-aws-modules/eks/aws` | 21.26.0 | Apache-2.0 | `infra/terraform/modules/eks` |
| `terraform-aws-modules/eks-pod-identity/aws` | 2.9.0 | Apache-2.0 | `infra/terraform/modules/eks`, `modules/platform` |

Built with (no modifications, standard library use — not a §13 reuse
record, just attribution): Spring Boot, PostgreSQL/PostGIS, Redis,
MinIO/AWS SDK v2, Micrometer, OpenTelemetry (backend); XGBoost,
scikit-learn, xarray, rasterio, `google-genai` (ML); React, Vite,
TypeScript, Vitest (frontend); Docker, Kubernetes, Terraform, GitHub
Actions (infrastructure). Data from NASA FIRMS, Copernicus CDS
(ERA5-Land), Copernicus DEM GLO-30, and ESA WorldCover — see **Data**
above.
