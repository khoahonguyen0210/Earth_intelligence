# Unit Test Pass

This pass checks unit test coverage of nine behaviors: data parsing, validation,
grid assignment, time windows, feature construction, API validation,
workflow states, retry/idempotency, and metric calculations. Each one
already had tests written together with the feature that introduced
it. This document records a run of the full suite showing that all
three components (the Python `ml` package, the Spring Boot backend and
the React frontend) still pass together. It does not add new tests.

## How to run it

```bash
# ml (from the repository root, not ml/; the distributed tests
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
and its sibling: both need the trained model artifact
(`ml/artifacts/...`) to be built first. This is an intended skip
condition (`pytest.mark.skipif`), not a gap; the rest of that file
tests the same code path with a stub model.

## Coverage by category

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

## Out of scope

- **No new tests were added.** Every category already had unit tests
  from the work that introduced it. This pass only checks that the full
  suite still passes together.
- **The integration and end-to-end tests are separate.** This pass
  runs each component's own tests, including the backend's
  `@SpringBootTest` classes that use a local Postgres and Redis (the
  backend has no unit tests with a mocked datasource left). It does not
  start the full Docker Compose or Kubernetes stack, as those other
  passes do.
