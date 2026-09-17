# Unit Test Pass — LOCKED

This document records the unit test pass. It is not a brainstorming
document.

It asks for coverage of nine behaviors: data parsing, validation,
grid assignment, time windows, feature construction, API validation,
workflow states, retry/idempotency, and metric calculations. Every one
of those was already exercised by tests written alongside the feature
that introduced it, across every earlier build phase; this document is
the full-suite run that proves all three components -- the Python `ml` package, the Spring
Boot backend, and the React frontend -- still pass together, not a
one-off addition of new tests for previously uncovered behavior.

## How to run it

```bash
# ml (from the repository root, not ml/ -- the distributed tests
# resolve their fixture data relative to cwd)
uv run --project ml pytest ml/tests -q

# backend (needs Postgres/Redis/MinIO: docker compose up -d from
# infra/docker/ first, per docs/persistence-schema.md)
cd backend && ./mvnw test

# frontend
cd frontend && npm test
```

Two environment quirks found while running this pass, neither a
product bug:

- **`ml/tests/distributed/*` must run with the repository root as the
  working directory.** Their fixture paths (e.g.
  `data/raw/firms/firms_sample.csv`) are relative, and running `pytest`
  from inside `ml/` instead of the repo root makes all 17 of those
  tests fail on `FileNotFoundError` even though nothing is wrong with
  the code under test.
- **`npm test` (Vitest) hangs and times out every worker when launched
  from this machine's Git Bash.** The same command run from PowerShell
  starts and finishes normally. Not investigated further since
  PowerShell is a supported shell here; noted so a future "unit tests
  are broken" report from Git Bash isn't taken at face value.

## Results

```text
ml (pytest)         531 passed, 2 skipped
backend (mvnw test)  173 passed
frontend (vitest)    49 passed
                     ---
                     753 passed, 2 skipped, 0 failed
```

The two ml skips are `test_run_forecast.py::test_predict_uses_the_real_trained_model`
and its sibling: both require the real trained model artifact
(`ml/artifacts/...`) to be built first, which is a deliberate skip
condition (`pytest.mark.skipif`), not a gap -- the same code path is
exercised against a stub model everywhere else in that file.

## Coverage by handbook category

```text
data parsing          ml: test_era5.py, test_firms.py, test_observation.py,
                           test_geography.py (DEM/landcover sampling)

validation             ml: test_validation.py (FIRMS/ERA5 row and schema checks)
                       backend: RequestShapeTest, RequestValidationIntegrationTest

grid assignment        ml: test_grid.py

time windows           ml: test_time_range.py

feature construction   ml: test_fire_history_features.py, test_environmental_features.py,
                           test_geography_features.py, test_labels.py,
                           test_build_dataset.py, test_leakage.py

API validation         backend: AnalysisControllerTest, ForecastControllerTest,
                           EarthQueryControllerTest, RequestShapeTest,
                           RequestValidationIntegrationTest, SecurityHeadersIntegrationTest,
                           RateLimitFilterTest, RateLimitIntegrationTest
                       frontend: ForecastRequestForm.test.tsx, AskEarthForm.test.tsx,
                           QueryForm.test.tsx

workflow states        backend: WorkflowStateMachineTest, WorkflowNodeTest, WorkflowTest,
                           WorkflowExecutorTest, WorkflowStoreTest,
                           WorkflowPartialFailureIntegrationTest, WorkflowTracingTest

retry/idempotency       backend: ForecastWorkerTest, RedisForecastQueueTest,
                           ForecastRecoveryIntegrationTest
                       frontend: ForecastPanel.test.tsx (job status polling)

metric calculations    ml: test_metrics.py, test_calibration.py, test_harness.py,
                           test_ablation.py
                       backend: ForecastMetricsTest, PrometheusEndpointIntegrationTest
```

`ml/tests/{planner,query,distributed,kubernetes}` and the remaining
frontend component tests (`ForecastMap.test.tsx`,
`EarthQueryResultView.test.tsx`, `ResultView.test.tsx`,
`RegionMap.test.tsx`, `App.test.tsx`) cover behavior outside these nine
categories (the natural-language planner, query dispatch, distributed
execution, Kubernetes benchmarks, map/result rendering) and are counted
in the totals above but not broken out here.

## What this task does not do

- **No new tests were added.** Every category the handbook names
  already had unit coverage from the phase that introduced it; this
  document is the verification that the full suite still passes together,
  matching the pattern of the earlier browser end-to-end verification.
- **The integration test pass and the end-to-end tests are
  separate efforts.** This pass exercises each component's own unit
  tests, including the backend's `@SpringBootTest` classes that talk to
  a real local Postgres/Redis (there is no mocked-datasource unit tier
  left in this codebase, see `backend`'s test suite above) -- but it
  does not stand up the full Docker Compose or Kubernetes stack the way
  those other test passes do.
