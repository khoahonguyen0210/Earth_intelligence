# End-to-End Test Pass — LOCKED

This document records the Task 15.3 end-to-end test pass, the third
task of Phase 15. It is not a brainstorming document.

Task 15.3 asks for four flows to be proven end to end, against the real
running system: earth analysis, forecast, worker failure, duplicate
request. All four already had real, non-mocked coverage from earlier
phases -- Task 14.5 (`docs/ask-earth.md`) drove earth analysis and
forecast at the API layer against a real backend, and Task 13.5
(`docs/reliability-tests.md`) drove worker failure and duplicate request
against a real backend under real, injected failures. This task re-runs
all four against the current code, and closes the one real gap Task
14.5 left open: at the time, no trained production model existed, so
the forecast leg only ever reached a `422`, never a genuine `SUCCEEDED`
prediction. `production_model_v1` has since been built, so this pass
gets a real successful forecast for the first time.

## What changed to make this pass possible

Running the real-model forecast test (`ml/tests/query/test_run_forecast.py
::test_run_forecast_end_to_end_on_real_history_and_the_trained_model`) as
part of this task's own setup surfaced a genuine test bug, not a product
bug: it asserted exact ERA5/FIRMS alignment at cutoff `2024-08-15T10:00:00Z`,
an off-grid hour. `build_historical_dataset.py`'s own cutoff rule only
produces weekly cutoffs (every 7 days from June 1 through October, 10:00
UTC), so ERA5's curated per-cutoff history has no snapshot of its own at
`08-15` -- `ERA5History.for_cutoff` correctly falls back to the latest
prior cutoff (`08-10`), which the test's exact-match assertion then
failed on. Fixed by moving the test to an on-grid cutoff
(`2024-08-10T10:00:00Z`), where alignment really is exact. Not a
pipeline defect: the fallback behavior itself is correct and already
covered by `test_require_lookback_coverage_accepts_a_fully_covered_lookback`
and its neighbors earlier in the same file.

## Setup for this pass

Real infrastructure throughout, nothing mocked:

```text
docker compose up -d          Postgres/PostGIS, Redis, MinIO, Jaeger
                               (infra/docker/docker-compose.yml)
./mvnw package -DskipTests    the real backend jar
java -jar ...jar              a real backend process, SERVER_PORT=8090,
                               pointed at the .venv Python for the
                               analysis/forecast/ask-earth subprocess
                               boundaries, GEMINI_API_KEY from .env
scripts/reliability/          the same harness Task 13.5 built: kills
  run_reliability_tests.py    and restarts real processes/containers
```

## Earth analysis: question → plan → dispatch → answer → evidence

`POST /queries {"question": "How many wildfires occurred in the Bay Area
during August 2024?"}` against the real Gemini API (one retry needed --
the first attempt hit a transient `503 UNAVAILABLE` from Gemini itself,
not a bug in this codebase) produced a real plan (`calculate_statistics`,
region `Bay Area`, `2024-08-01`–`2024-09-01`), real dispatch against the
real FIRMS history, and a grounded answer:

```json
{
  "answer": "There were 245 wildfires in the Bay Area during August 2024 (computed).",
  "facts": [{
    "result": {"count": 245},
    "evidence": {
      "dataset": "NASA_FIRMS:VIIRS_SNPP_SP",
      "region_label": "bay_area", "region_bbox": [-123.3, 36.9, -121.2, 38.9],
      "period_start": "2024-08-01T00:00:00+00:00", "period_end": "2024-09-01T00:00:00+00:00"
    }
  }]
}
```

Answer, count, and evidence (dataset, region, time range) all present
and consistent with each other -- the same shape `EarthQueryResultView`
renders.

## Forecast: submit → job → status → real prediction → calibration → evidence

`POST /forecasts {"region": {"kind": "named", "value": "california"},
"cutoff": "2024-08-10T10:00:00Z"}` (an on-grid weekly cutoff, matching
the test fix above) created a real job, observed live over its real
`PENDING → RUNNING → SUCCEEDED` transition (`ForecastWorker` picked it
up from the real Redis queue and ran the real trained model), and
`GET /forecasts/{id}/result` returned a genuine, fully populated result
-- the first time this pipeline has produced one outside a unit test:

```text
model_version         v1 (xgboost + isotonic calibration)
data_cutoff           2024-08-10T10:00:00+00:00
forecast_window       2024-08-10T10:00:00Z -> 2024-08-11T10:00:00Z (24h)
grid features          9,975 cells, probability in [0.0, 1.0]
calibration             2 bins
evidence               dataset wildfire_forecast:v1, region california,
                        firms_observations 8,626, model trained on
                        877,800 rows / 88 cutoffs (2019-06-01 -> 2022-10-26)
```

This closes the exact gap Task 14.5 flagged: a real `SUCCEEDED`
prediction, real probabilities, and a real calibration table, not just
the response contract.

## Worker failure and duplicate request: `run_reliability_tests.py`

Re-run in full (`ml/artifacts/reliability_tests/task-15-3.json`) against
the current code, all seven scenarios still pass:

```text
PASS  duplicate request          SUCCEEDED       2.6s
PASS  job timeout (recovers)     SUCCEEDED       1.3s
PASS  job timeout (gives up)     FAILED         61.0s
PASS  Redis unavailable          SUCCEEDED      20.6s
PASS  database unavailable       SUCCEEDED      14.6s
PASS  worker crash               SUCCEEDED      90.6s
PASS  malformed Earth data       FAILED          0.0s
```

The two this task specifically asks for:

- **Duplicate request.** Ten concurrent `POST /forecasts` sharing one
  `Idempotency-Key`: nine got `200` (re-reading the same row), one got
  `201`; every response named the same `forecast_id`; exactly one row
  exists in Postgres. Detected by the unique index on `idempotency_key`
  alone -- no recovery step needed, since the duplicates never became
  separate jobs in the first place.
- **Worker crash.** The real backend process tree was hard-killed
  (`taskkill /T`, no shutdown hooks) while a job was `RUNNING`, then
  restarted. The restarted backend's `ForecastRecovery` sweep found the
  orphaned `RUNNING` row (older than `forecast.python.timeout-seconds`
  plus its grace period), marked it a lost attempt, and retried it; the
  job reached `SUCCEEDED` on its second attempt, 90.6s after the crash
  (71.5s of that is the backend's own real cold-start).

Full detection/recovery/observation detail for all seven, including the
five already covered under Task 13.5, is in `docs/reliability-tests.md`;
this run only re-confirms they still hold on the current code, it does
not re-derive them.

## What this task does not do

- **Does not re-litigate Task 13.5's fixes.** `ForecastRecovery`, the
  atomic `claim`, and the dependency-outage handling are unchanged by
  this task; this pass only re-runs the harness that proves they still
  work.
- **Does not add a browser-automation layer.** As in Task 14.5, this
  environment has no browser-automation tool; earth analysis and
  forecast are driven at the API layer with the exact requests the
  frontend's own `client.ts` issues, against a real backend and real
  infra -- not a rendering-level check. The React component tests
  (`AskEarthForm`, `ForecastPanel`, `ForecastMap`, ...) already cover
  the rendering layer this does not.
- **Does not exercise a second, independent question or region for
  earth analysis/forecast.** One real run of each is enough to prove
  the pipeline works end to end with a genuine trained model; repeat
  runs would exercise the same code paths without new evidence.
