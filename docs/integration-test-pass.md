# Integration Test Pass — LOCKED

This document records the Task 15.2 integration test pass, the second
task of Phase 15. It is not a brainstorming document.

Task 15.2 asks for the real boundaries to be tested: Spring API ↔
PostgreSQL/PostGIS, ↔ Redis, ↔ object storage, ↔ Python worker. This
codebase has no separate unit-vs-integration test tier to run
independently -- Task 6.3 removed the last mocked-datasource path
(`BackendApplicationTests` needs a live datasource to even boot Spring),
and every subsequent phase kept that decision rather than reintroducing
a fake-infrastructure tier. So `./mvnw test` (the same command Task 15.1
already ran) *is* the integration test pass for the backend; this task
is the check that it actually exercises all four boundaries, not a
second, separate test run.

## Evidence per boundary

```text
Spring API <-> Postgres/PostGIS
    BackendApplicationTests, WorkflowStoreTest, ForecastRecoveryIntegrationTest,
    RequestValidationIntegrationTest, StructuredLoggingIntegrationTest,
    OpsSurfaceIntegrationTest, RateLimitIntegrationTest,
    SecurityHeadersIntegrationTest, WorkflowPartialFailureIntegrationTest,
    TracingIntegrationTest, EarthQueryIntegrationTest, PrometheusEndpointIntegrationTest
    -- all @SpringBootTest classes that boot the full app against the real
    docker-compose Postgres (Flyway-migrated schema), not a mock or an
    in-memory substitute.

Spring API <-> Redis
    RedisForecastQueueTest (real Lettuce connection, real LPUSH/RPOP),
    RateLimitFilterTest/RateLimitIntegrationTest (real token-bucket state
    in Redis), ForecastMetricsTest, ForecastRecoveryIntegrationTest, and
    TracingIntegrationTest (real queue enqueue/dequeue inside a live
    request).

Spring API <-> object storage
    S3ObjectStoreTest proves the actual put/get/exists/delete wiring
    against real local MinIO. This is the one boundary with no
    production caller to integration-test through a full request --
    see "What this does not cover" below; it is not an oversight, it is
    Task 6.4's own documented scope (docs/object-storage-contract.md:
    "No Java caller writes through this abstraction yet").

Spring API <-> Python worker
    PythonForecastRunnerTest and PythonEarthQueryRunnerTest spawn the
    real python interpreter against small fixture scripts under
    src/test/resources, proving the actual process boundary (argv,
    stdin/stdout JSON, exit codes, timeout-and-kill, transient-vs-
    permanent failure classification) rather than a stubbed-out
    interface. TracingIntegrationTest and EarthQueryIntegrationTest
    exercise the same process boundary inside a real, running Spring
    Boot app end to end: a real HTTP POST creates a Postgres row, a
    real Redis enqueue/dequeue hands it to ForecastWorker, and a real
    python subprocess runs and returns a result that is written back
    to Postgres and visible on a real HTTP GET.
```

## Results

One clean run, `./mvnw clean test`, against the same local
`docker compose up -d` stack (Postgres/PostGIS, Redis, MinIO) Task 15.1
used:

```text
173 passed, 0 failed, 0 errors
```

**A pitfall hit while producing this number, worth recording:** running
two `mvnw test` invocations concurrently against the same checkout
produces spurious failures -- observed as
`PythonEarthQueryRunnerTest.returnsFailureForANonZeroExit` failing with
"the pipe is being closed" (a Windows process-pipe error from two JVMs'
worker fixture processes and shared `target/surefire-reports` output
colliding), and the total failure count climbing as both runs
progressed. Confirmed as a test-running mistake rather than a product
bug two ways: the same test class alone, rerun in isolation, passed; and
a single clean run afterward (the 173/0 above) also passed. Don't run
concurrent `mvnw test` against one checkout -- it shares local Redis,
ports, and `target/` with itself.

## What this does not cover

- **Object storage has no boundary test through a real request**,
  because nothing in the product calls it yet (Task 6.4's own documented
  decision, not a gap this task invents scope to close). `S3ObjectStoreTest`
  is the honest ceiling of what can be integration-tested today: the
  abstraction against real MinIO, not a controller-to-MinIO round trip
  that doesn't exist.
- **The CLI wrapper scripts themselves
  (`scripts/query/run_forecast_cli.py`/`run_analysis_cli.py`/
  `run_ask_earth_cli.py`) are never run as a real subprocess with the
  real ML pipeline behind them.** Each is ~10 lines (read stdin JSON,
  call the real function, write stdout JSON, exit 1 on error); the
  function each calls is covered by `ml/tests` directly, and the
  stdin/stdout/exit-code protocol itself is covered from the Java side
  by `PythonForecastRunnerTest`/`PythonEarthQueryRunnerTest` against
  fixture scripts speaking the identical protocol. Building a fixture
  that runs the real CLI with a real trained model and real FIRMS/ERA5/
  geography data was already tried and dropped at Task 13.5
  (`docs/reliability-tests.md`, "malformed-data forecast leg") for the
  same reason: it needs a full model-plus-data fixture a directory of
  sample rows can't stand in for. Not reattempted here.
- **No Kubernetes-level or Docker-Compose-level integration test.**
  Those exist already, one layer up (Tasks 10.3, 11.3, 13.5) and are out
  of scope for this task, which is specifically the Spring API's own
  boundaries.
