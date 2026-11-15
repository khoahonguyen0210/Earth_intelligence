# Integration Test Pass

This pass tests the backend's boundaries: Spring API to
PostgreSQL/PostGIS, to Redis, to object storage and to the Python
worker. The backend has no separate unit and integration test levels.
An earlier change removed the last mocked datasource
(`BackendApplicationTests` needs a live datasource to start Spring), and
later work kept it that way. So `./mvnw test`, the same command as the
unit test pass, is also the integration test pass. This document checks
that it covers all four boundaries; it is not a second test run.

## Evidence per boundary

```text
Spring API <-> Postgres/PostGIS
    BackendApplicationTests, WorkflowStoreTest, ForecastRecoveryIntegrationTest,
    RequestValidationIntegrationTest, StructuredLoggingIntegrationTest,
    OpsSurfaceIntegrationTest, RateLimitIntegrationTest,
    SecurityHeadersIntegrationTest, WorkflowPartialFailureIntegrationTest,
    TracingIntegrationTest, EarthQueryIntegrationTest, PrometheusEndpointIntegrationTest
    All are @SpringBootTest classes that start the full app against the
    docker-compose Postgres (schema migrated by Flyway), not a mock or an
    in-memory database.

Spring API <-> Redis
    RedisForecastQueueTest (a Lettuce connection, LPUSH/RPOP),
    RateLimitFilterTest and RateLimitIntegrationTest (token-bucket state
    in Redis), ForecastMetricsTest, ForecastRecoveryIntegrationTest and
    TracingIntegrationTest (queue enqueue and dequeue inside a live
    request).

Spring API <-> object storage
    S3ObjectStoreTest tests put, get, exists and delete against a local
    MinIO. No production code calls object storage yet, so there is no
    full request to test through. This follows the documented scope in
    docs/object-storage-contract.md: "No Java caller writes through this
    abstraction yet". See "Not covered" below.

Spring API <-> Python worker
    PythonForecastRunnerTest and PythonEarthQueryRunnerTest start the
    Python interpreter on small fixture scripts under
    src/test/resources. They test the process boundary itself (argv,
    stdin/stdout JSON, exit codes, timeout and kill, and the split
    between temporary and permanent failures), not a stub.
    TracingIntegrationTest and EarthQueryIntegrationTest test the same
    boundary inside a running Spring Boot app: an HTTP POST creates a
    Postgres row, a Redis enqueue and dequeue hands it to
    ForecastWorker, and a Python subprocess returns a result that is
    written to Postgres and returned by an HTTP GET.
```

## Results

One clean run of `./mvnw clean test`, against the same local
`docker compose up -d` stack (Postgres/PostGIS, Redis, MinIO) as the
unit test pass:

```text
173 passed, 0 failed, 0 errors
```

**Do not run two test runs at once.** Two `mvnw test` runs on the same
checkout at the same time caused false failures. For example,
`PythonEarthQueryRunnerTest.returnsFailureForANonZeroExit` failed with
"the pipe is being closed", a Windows pipe error caused by the fixture
processes of two JVMs and their shared `target/surefire-reports` output
getting in each other's way. The failure count grew as both runs went
on. Two checks showed that this was a mistake in how the tests were run,
not a product bug: the same test class passed when run alone, and a
single clean run afterward passed (the 173/0 above). Concurrent runs on
one checkout share the local Redis, ports and `target/` folder.

## Not covered

- **Object storage is not tested through a full request**, because
  nothing in the product calls it yet. This is a documented decision of
  the object storage contract. `S3ObjectStoreTest` is the most that can
  be tested today: the abstraction against MinIO, not a controller to
  MinIO round trip that does not exist.
- **The CLI wrapper scripts
  (`scripts/query/run_forecast_cli.py`, `run_analysis_cli.py`,
  `run_ask_earth_cli.py`) are not run as subprocesses with the ML
  pipeline behind them.** Each is about 10 lines: read JSON from stdin,
  call a function, write JSON to stdout and exit 1 on error. `ml/tests`
  covers each function directly, and on the Java side
  `PythonForecastRunnerTest` and `PythonEarthQueryRunnerTest` cover the
  stdin, stdout and exit-code protocol with fixture scripts that use the
  same protocol. A fixture that runs a CLI with a trained model and full
  FIRMS, ERA5 and geography data was tried before and dropped
  (`docs/reliability-tests.md`, "malformed-data forecast leg"). It needs
  a full model and data set that a folder of sample rows cannot replace.
- **There is no Kubernetes or Docker Compose integration test here.**
  Those exist one level up. This pass covers only the Spring API's own
  boundaries.
