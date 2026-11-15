# Ask Earth

Ask Earth takes a question in plain English and returns an answer,
numbers, a map and evidence. This document covers the page and the
backend behind it.

## Why it needs a backend

The older routes, `POST /analyses` and `POST /forecasts`, need a region,
a time range and an operation that are already resolved. A question in
plain English has none of these. Before this work, nothing in the code
turned a question into an executed result: the planner produced a plan,
but no part of the system ran it. Ask Earth adds three parts: a Python
dispatch module, a backend resource and the page itself.

## Pipeline

```text
question
  -> generate_plan (Gemini, structured output)
  -> validate_plan_or_raise (generate_plan already calls
     this; an invalid plan never reaches dispatch)
  -> execute_plan (new: query/dispatch.py)
  -> generate_answer (Gemini, grounded only in real outputs)
```

`run_ask_earth(payload, client, backend)` in `query/run_ask_earth.py`
runs the whole pipeline. Like `run_analysis.py` and `run_forecast.py`,
it takes its dependencies as parameters and keeps no global state.
`scripts/query/run_ask_earth_cli.py` is a thin stdin/stdout wrapper that
`PythonEarthQueryRunner` (below) calls as a subprocess, in the same way
as `run_analysis_cli.py` and `run_forecast_cli.py`.

## Dispatch

`execute_plan` in `query/dispatch.py` runs the steps of a validated
`Plan` in dependency order. It replaces each `$step_id.field` reference
with the output of the earlier step. The validator has already checked
that every reference is well formed. If a step fails, the steps that
depend on it never run, and `StepFailed` lists every failure. The
dispatcher never returns a partial answer.

```text
resolve_region        query.region.normalize_region
get_data               real record counts (region- and time-filtered,
                       not merely the whole ingested file) + real
                       provenance (data.provenance.build_provenance)
calculate_statistics   query.run_analysis, operation != "map"
generate_map           query.run_analysis, operation == "map"
run_forecast           the real POST /forecasts, polled to a terminal
                       status
get_result_evidence    GET /forecasts/{id}/result's own evidence
```

Two of these steps needed more than a function call:

- **`get_data` counts records by region as well as by time.** The first
  version counted every observation in the time window
  (`len(observations)`). It now uses `query.statistics.count`, the same
  count that `calculate_statistics` uses, so the two steps agree.
  `ERA5History.for_cutoff` returns every grid cell in its lookback
  window, because the forecast pipeline always needs the whole
  California grid. The dispatcher filters those records to the
  requested bounding box itself.
- **`run_forecast` and `get_result_evidence` call the HTTP API.** A step
  could call `query.run_forecast.run_forecast(...)` directly, but that
  would skip idempotency, retries, tracing and, most importantly,
  `ForecastRecovery`. Going through `POST /forecasts` gives a plan's
  forecast step all of these.

Testing this dispatch against the running backend found a bug in
`ServerPort`, described below. A test with only mocks would have missed
it.

## Backend resource: `EarthQuery`

The routes are `POST /queries`, `GET /queries/{id}` and
`GET /queries/{id}/result`. They follow the shape of
`AnalysisController`: results are stored in Postgres
(`V6__earth_queries.sql`), and the request is synchronous. There is no
queue; the request thread waits for one call to `PythonEarthQueryRunner`.
`EarthQueryRequest` is just `{question}`, with the same size limits as
`AnalysisRequest.question` (`RequestShape`). `POST /queries` has its own
rate limit (`RateLimitFilter`, `api.rate-limit.queries-per-minute`,
default 20/min), because each request starts an LLM call and runs a
whole plan. `/forecasts` and `/analyses` are limited for the same
reason.

`PythonEarthQueryRunner` follows `PythonForecastRunner` rather than the
simpler `PythonAnalysisRunner`. A plan can include a `run_forecast` step,
whose polling can take up to `Backend.max_wait_seconds` (150 s), and
`generate_map` can return a large `FeatureCollection`. So the runner has
a time limit (`ask-earth.python.timeout-seconds`, default 180 s) and
reads stdout and stderr on separate threads. This avoids the deadlock
that occurs when an OS pipe buffer fills up.

### `ServerPort` and the bug it found

For `run_forecast` and `get_result_evidence` steps, the Python
subprocess calls back into the same backend, so it needs the port the
backend is bound to. This port is not known when the bean is built:
`@Value("${server.port}")` is `0` under
`@SpringBootTest(webEnvironment = RANDOM_PORT)`. `ServerPort` therefore
listens for Spring Boot's `WebServerInitializedEvent` and is read at
request time.

With a separate `management.server.port`, Spring Boot starts two
embedded web servers, and each fires its own `WebServerInitializedEvent`.
`EarthQueryIntegrationTest`, which runs the full application, caught
the problem at once: the event that fired second won, so the subprocess
sometimes received the management port. `ServerPort` now checks
`WebServerApplicationContext.getServerNamespace()`, which is `null` or
`""` for the main server and `"management"` for the other, and ignores
the management server.

## The Ask Earth page

`AskEarthForm` has the question input, the submit button and the list
of recent queries. `App.tsx` handles the loading, error and success
states. The page calls `createEarthQuery` and then `getEarthQueryResult`
(`api/client.ts`), matching the synchronous `POST /queries`, in the same
way as `createAnalysis` and `getAnalysisResult`.

Recent queries are kept in `localStorage` (`ai-earth:recent-queries`, at
most 8, no duplicates, newest first). This is a per-browser
convenience. Storage access can throw in private browsing or when site
data is blocked, so it is wrapped in `try`/`catch`, and nothing else
depends on it. Clicking a recent query fills the input but does not
submit it.

This page replaces the earlier structured form (`QueryForm`,
`ResultView`, `RegionMap`) as the content of `App.tsx`. The product is
designed around questions in plain English, and the structured form was
a temporary interface built before the planner existed. The old
components and their tests remain in the code and still pass, because
`POST /analyses` is still a working and useful route.

## The result page

`EarthQueryResultView` shows the full result for each fact: answer,
map, numbers, time, region and evidence. A plan can produce more than
one fact, for example a count and a forecast. `RegionMap` is reused
without changes, because it only needs a bounding box and a label, and
each fact's `Evidence` already has both.

Each fact's `result` is recognized by its shape, as in `ResultView`
(`CountResult`, `DailyAggregateResult`, `WeeklyAggregateResult`,
`MapResult`). Two shapes are new to this pipeline: `DatasetReference`
(from `get_data`: source, product, record count, provenance) and
`ForecastJobReference` (from `run_forecast`: only
`{forecast_id, status}`, because `docs/forecast-api-contract.md` states
that this route creates a forecast job and does not compute it).
Region, time and evidence appear only when a fact has its own
`Evidence`, which is true for `calculate_statistics` and `generate_map`.
Facts from `get_data` and `run_forecast` have none, so those sections
are left out instead of showing empty or invented values.

A `run_forecast` fact shows only the job reference, not a risk grid.
The grid belongs to the forecast map, which needs fields (legend,
forecast window, calibration) that the general result view does not
have.

## The forecast map

`ForecastMap` (`frontend/src/components/ForecastMap.tsx`) renders the
response of `GET /forecasts/{id}/result`. It was written against the
code, not only against `docs/forecast-api-contract.md`. The example JSON
in that document shows a flat `FeatureCollection`, but
`forecast_result_to_dict` (`ml/.../query/forecast_result.py`) nests it
under a top-level `grid` key, next to `model_version`, `data_cutoff`,
`forecast_window`, `calibration` and `evidence`.

The map shows:

- the California grid, one colored `<rect>` per feature, projected on
  the same reference bounding box as `RegionMap` so both maps share a
  scale;
- each cell's `probability`, a legend, the forecast window
  (`forecast_window`), the data cutoff and the model version;
- the calibration table and the forecast's evidence.

Probability is a quantity, so it uses a sequential blue scale split
into 7 bins. The scale runs from the grid's lowest to highest
probability, not from 0 to 1, and the legend shows both ends. Wildfire
probabilities are mostly close to zero, so a fixed 0 to 1 scale would
make almost every cell the same color. Each cell also has an SVG
`<title>` with its tile ID and probability, shown on hover. A full,
sortable table of all cells sits under a `<details>` toggle, so the
values never depend on color alone.

The component only renders a forecast that has already `SUCCEEDED`. It
takes a `ForecastResult` as a prop, in the same way that `RegionMap`
takes only a bounding box and a label. Fetching a forecast and handling
PENDING, RUNNING and FAILED belong to the job-status panel below.

## Job-status panel

`ForecastPanel` (`frontend/src/components/ForecastPanel.tsx`) is a
second section of the page, next to Ask Earth. It is separate on
purpose. `dispatch_run_forecast` in `query/dispatch.py` polls
`POST /forecasts` on the server until the job finishes, before the
`/queries` response is sent. So by the time a `ForecastJobReference`
reaches the browser, the job is already finished, and there is no
progress to show. A queued, running, completed or failed display needs
a job that the browser watches while it runs. That means the direct,
asynchronous `POST /forecasts` route, submitted through a new
`ForecastRequestForm` (region and cutoff only, with the same region
fields as `QueryForm`).

`ForecastPanel` submits the job and then polls `GET /forecasts/{id}`
(`getForecastStatus` in `api/client.ts`) every 2 s until
`Forecast.Status` reaches a final value. The server-side poll in
`dispatch_run_forecast` uses `poll_interval_seconds=1.0`, so 2 s is of
the same order and does not flood the endpoint. On success the panel
fetches `GET /forecasts/{id}/result` and renders `ForecastMap`. On
failure it shows the backend's error message.

The panel never shows an invented progress percentage. Its four states
map the six backend values directly:

- PENDING and RETRYING both show as "queued", because both are waiting
  for an attempt.
- CANCELLED shows as "failed", because it is a final state without
  success. No cancel endpoint exists, so it cannot occur at present.

The backend status string is always shown next to the mapped label.
Each status has a shape, a text label and the raw value, so its meaning
never depends on color alone.

**Bug found.** Testing `ForecastPanel` against the running backend, not
only with a mocked client, showed that every Forecast response field is
written in `snake_case` (`spring.jackson.property-naming-strategy=SNAKE_CASE`
in `application.properties`). `POST /forecasts` returns
`{"forecast_id": ..., "status": ...}`, not the `forecastId` that the
first draft took from the Java field name in `ForecastSummaryResponse`.
`ForecastResultResponse` has the same field. The other response types
(`EarthQuerySummaryResponse`, `ResultResponse` and others) use one-word
field names such as `id`, `status` and `result`, which are the same in
both styles. That is why the problem had not appeared before. The fix
renames `forecastId` to `forecast_id` in `ForecastSummary` and
`ForecastResultResponse`. This follows the existing rule of typing a
response exactly as it appears on the wire; `Evidence`, `CalibrationBin`
and others already use snake_case.

## Out of scope

- **Ask Earth's own `run_forecast` fact has no status display.** Its
  forecast step has already finished when the `/queries` response
  exists, so a `run_forecast` fact still shows only its job reference.
- **`WorkflowExecutor` is unchanged.** `execute_plan` is a separate,
  simple executor for one synchronous Ask Earth request. It runs steps
  in order and does not persist them.
- **Malformed input is not tested again here.** A corrupt FIRMS row
  already fails cleanly while the service stays up. `execute_plan` calls
  `run_analysis` and `POST /forecasts` without changes, so those
  guarantees still hold.

## Tests

```text
ml/tests/query/test_dispatch.py         14  every dispatch_* function against real
                                             fixtures (a real FIRMS CSV, a real ERA5
                                             NetCDF, region-filtered counts); run_forecast/
                                             get_result_evidence mocked at the HTTP boundary
                                             (tests/data/test_firms.py's own pattern);
                                             execute_plan's ordering, ref substitution,
                                             and cancellation of a failed step's dependents
ml/tests/query/test_run_ask_earth.py     3  the whole pipeline, a faked Gemini client (the
                                             same fake as test_generate_plan.py/
                                             test_generate_answer.py), real dispatch against
                                             a real FIRMS fixture; a plan that fails
                                             validation, and a step that fails, both raise
                                             before reaching the answer call
EarthQueryControllerTest                 9  mirrors AnalysisControllerTest
PythonEarthQueryRunnerTest                5  mirrors PythonForecastRunnerTest; checks that
                                             the subprocess receives ASK_EARTH_BACKEND_BASE_URL
EarthQueryIntegrationTest                 3  the full app, Postgres, and the ServerPort
                                             event wiring (not the unit tests' manual
                                             setForTest); this caught the management-port bug
RateLimitFilterTest                     +1  /queries has its own configured limit
AskEarthForm.test.tsx                     7  submit, blank-question rejection, loading
                                             state, recent-queries persistence/ordering/
                                             deduplication, click-to-fill without resubmitting
App.test.tsx                              4  shell + backend status; a question answered
                                             end to end; an error surfaced; the form
                                             disabled while asking
EarthQueryResultView.test.tsx             8  answer always shown; count/daily/weekly/map
                                             facts rendered with region+time+evidence;
                                             get_data/run_forecast facts with none of
                                             their own show no region/time/evidence
                                             section; a run_forecast fact is a job
                                             reference only; multiple facts each in their
                                             own step
ForecastMap.test.tsx                      6  one colored cell per grid feature with
                                             a hover title; model version/data cutoff/
                                             forecast window shown; legend spans the
                                             grid's min/max probability;
                                             calibration table and full per-cell table
                                             view both present; the forecast's
                                             evidence shown
ForecastRequestForm.test.tsx               4  named/bbox/coordinates region submission;
                                             cutoff read as UTC; disabled while a job
                                             is already in flight
ForecastPanel.test.tsx                     4  initial status shown right after
                                             submit, form disabled meanwhile; the
                                             result rendered once the backend reports
                                             SUCCEEDED; the backend error shown on
                                             FAILED; the submission error shown when
                                             the job cannot be created
```

Two live runs against the Gemini API and the FIRMS history also checked
the pipeline end to end. The question "How many fires occurred in
California between August 1 and August 5, 2024?" produced a plan
(`calculate_statistics`, region `california`, and the model's reading
of the date range), a count from `data/raw/firms/history`, and a
grounded answer. In one run, the answer pointed out that the plan's
half-open time window did not exactly match the wording of the
question, instead of stating a number that only sounded exact.

Test totals after this work: backend **173 tests, 0 failures** (155
before); `ml` **528 -> 545 tests** (17 new, for `dispatch.py` and
`run_ask_earth.py`), 0 failures, 2 skipped (the forecast tests that need
the trained model); frontend **49 tests, 0 failures** (19 before).

## End-to-end check through the API

Both flows were run through the API with the same requests that
`client.ts` sends (same URLs, methods and bodies), against a freshly
built backend and the Docker Compose services (Postgres, Redis, MinIO).
Nothing was mocked or replayed. This checks everything a browser would
do except drawing the page, so a rendering bug, such as a JSX typo or a
missing prop, would not show up here. The component tests cover that
part.

**Stale backend found.** Before the check, `curl
http://localhost:8080/readyz` returned a healthy response, but
`POST /queries` returned 404. Port 8080 was being served by an old
`ai-earth-backend` image in a local kind Kubernetes cluster, built
before `EarthQueryController` existed. A fresh backend was started with
`./mvnw spring-boot:run` on `SERVER_PORT=8090` and `MANAGEMENT_PORT=8091`,
against the same Docker Compose services, and every check below ran
against that build.

### Earth question -> planner -> validated workflow -> computation -> result -> map -> evidence

`POST /queries {"question": "Show me a map of wildfire counts across
the Bay Area in August 2024"}` produced a plan with `generate_map`,
region `bay area`, and the time range 2024-08-01 to 2024-09-01 (the
model's reading of "August 2024"). The plan passed validation, dispatch
ran it against the FIRMS history, and the result was a
`FeatureCollection` fact: one polygon (the Bay Area bounding box),
`properties.value: 245`, `units: "fire_count"`. The answer ("The Bay
Area recorded 245 wildfire counts during August 2024 (computed)...")
and the fact's `evidence` (`dataset: "NASA_FIRMS:VIIRS_SNPP_SP"`,
`region_bbox`, `period_start`/`period_end`, `query_parameters`) matched
the shape that `EarthQueryResultView.tsx` expects, field for field. The
`isMapResult` branch would render `"bay_area: 245 fire_count"`, and the
evidence section would show the dataset, region and time range.

### Forecast question -> job -> status -> prediction -> uncertainty -> evidence

`POST /forecasts` for the same region created a job
(`{"forecast_id": ..., "status": "PENDING"}`). Polling
`GET /forecasts/{id}` showed the transition PENDING -> RUNNING -> FAILED:
`ForecastWorker` took the job from the Redis queue and ran it.
`GET /forecasts/{id}/result` returned
`422 {"error": "no trained production model at ml/artifacts/
production_model_v1 -- run scripts/models/train_production_model.py
first"}`, which is the shape that `ForecastPanel` expects and shows as
an alert.

The machine used for this check had no trained `production_model_v1`,
so a successful prediction with probabilities and a calibration table
was not run here. The component tests cover how `ForecastMap` and
`ForecastPanel` handle that response. A successful forecast over 9,975
grid cells is shown in `docs/forecasting-demo.md`.
