# End-to-End Test Pass

This pass checks four flows end to end on the running system: Earth
analysis, forecast, worker failure and duplicate request. Each flow
already had tests without mocks. `docs/ask-earth.md` ran Earth analysis
and forecast through the API against a running backend, and
`docs/reliability-tests.md` ran worker failure and duplicate request
against a running backend with injected failures. This pass runs all
four again on the current code.

It also closes one gap. When `docs/ask-earth.md` was written, no trained
production model existed, so the forecast flow could only reach a
`422`. `production_model_v1` has since been built, so this pass
includes a successful forecast for the first time.

## Test fix needed first

The forecast test that uses the trained model
(`ml/tests/query/test_run_forecast.py
::test_run_forecast_end_to_end_on_real_history_and_the_trained_model`)
failed because of a bug in the test, not in the product. It expected
ERA5 and FIRMS data to line up exactly at cutoff `2024-08-15T10:00:00Z`,
which is not on the cutoff grid. `build_historical_dataset.py` makes
only weekly cutoffs (every 7 days from June 1 through October, at 10:00
UTC), so the stored ERA5 history has no snapshot for `08-15`.
`ERA5History.for_cutoff` correctly falls back to the latest earlier
cutoff (`08-10`), and the exact-match check then failed. The test now
uses a cutoff on the grid (`2024-08-10T10:00:00Z`), where the data does
line up exactly. The fallback itself is correct and is covered by
`test_require_lookback_coverage_accepts_a_fully_covered_lookback` and
the tests near it in the same file.

## Setup

All services were real; nothing was mocked:

```text
docker compose up -d          Postgres/PostGIS, Redis, MinIO, Jaeger
                              (infra/docker/docker-compose.yml)
./mvnw package -DskipTests    the backend jar
java -jar ...jar              a backend process, SERVER_PORT=8090,
                              using the .venv Python for the analysis,
                              forecast and Ask Earth subprocesses, and
                              GEMINI_API_KEY from .env
scripts/reliability/          the existing harness, which kills and
  run_reliability_tests.py    restarts processes and containers
```

## Earth analysis: question → plan → dispatch → answer → evidence

`POST /queries {"question": "How many wildfires occurred in the Bay Area
during August 2024?"}` was sent to the Gemini API. The first attempt
got a temporary `503 UNAVAILABLE` from Gemini, so it was retried once.
The result was a plan (`calculate_statistics`, region `Bay Area`,
`2024-08-01` to `2024-09-01`), dispatch against the FIRMS history, and
a grounded answer:

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

The answer, the count and the evidence (dataset, region and time range)
are all present and agree with each other. This is the shape that
`EarthQueryResultView` renders.

## Forecast: submit → job → status → prediction → calibration → evidence

`POST /forecasts {"region": {"kind": "named", "value": "california"},
"cutoff": "2024-08-10T10:00:00Z"}` uses a weekly cutoff on the grid, as
in the test fix above. It created a job that moved through
`PENDING → RUNNING → SUCCEEDED`: `ForecastWorker` took it from the
Redis queue and ran the trained model. `GET /forecasts/{id}/result`
returned a complete result, the first one produced outside a unit test:

```text
model_version         v1 (xgboost + isotonic calibration)
data_cutoff           2024-08-10T10:00:00+00:00
forecast_window       2024-08-10T10:00:00Z -> 2024-08-11T10:00:00Z (24h)
grid features         9,975 cells, probability in [0.0, 1.0]
calibration           2 bins
evidence              dataset wildfire_forecast:v1, region california,
                      firms_observations 8,626, model trained on
                      877,800 rows / 88 cutoffs (2019-06-01 -> 2022-10-26)
```

This closes the gap noted in `docs/ask-earth.md`: a `SUCCEEDED`
prediction with probabilities and a calibration table, not only the
response format.

## Worker failure and duplicate request

`run_reliability_tests.py` was run in full on the current code
(`ml/artifacts/reliability_tests/end_to_end.json`). All seven scenarios
still pass:

```text
PASS  duplicate request          SUCCEEDED       2.6s
PASS  job timeout (recovers)     SUCCEEDED       1.3s
PASS  job timeout (gives up)     FAILED         61.0s
PASS  Redis unavailable          SUCCEEDED      20.6s
PASS  database unavailable       SUCCEEDED      14.6s
PASS  worker crash               SUCCEEDED      90.6s
PASS  malformed Earth data       FAILED          0.0s
```

The two flows in scope here:

- **Duplicate request.** Ten concurrent `POST /forecasts` requests
  shared one `Idempotency-Key`. Nine got `200` (reading the same row)
  and one got `201`. Every response named the same `forecast_id`, and
  Postgres holds exactly one row. The unique index on `idempotency_key`
  prevents the duplicates by itself; no recovery is needed, because the
  duplicates never become separate jobs.
- **Worker crash.** The backend process tree was killed hard
  (`taskkill /T`, no shutdown hooks) while a job was `RUNNING`, and then
  restarted. On start, `ForecastRecovery` found the orphaned `RUNNING`
  row (older than `forecast.python.timeout-seconds` plus its grace
  period), marked the attempt as lost and retried it. The job reached
  `SUCCEEDED` on its second attempt, 90.6 s after the crash; 71.5 s of
  that was the backend starting up.

`docs/reliability-tests.md` has the full detection, recovery and
observation detail for all seven scenarios. This run only confirms that
they still pass on the current code.

## Out of scope

- **Earlier reliability fixes are unchanged.** `ForecastRecovery`, the
  atomic `claim` and the handling of outages are not modified here.
  This pass only reruns the harness that tests them.
- **There is no browser automation.** Earth analysis and forecast are
  run through the API with the same requests that the frontend's
  `client.ts` sends, against a running backend and services. This does
  not check rendering. The React component tests (`AskEarthForm`,
  `ForecastPanel`, `ForecastMap` and others) cover rendering.
- **Each flow runs once.** One run of each shows that the pipeline works
  end to end with the trained model. More runs would use the same code
  paths and add no new evidence.
