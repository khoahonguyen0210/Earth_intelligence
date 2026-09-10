# Ask Earth — LOCKED

This document freezes the Ask Earth page and its backend per Task 14.1
of the Execution Handbook, the first task of Phase 14. It is not a
brainstorming document.

## Why this task is more than a frontend page

Task 14.1 asks for a page with "natural-language input." Every existing
route (`POST /analyses`, `POST /forecasts`) already requires a *resolved*
region, time range and operation -- exactly what a natural-language
question does not carry. Building a real natural-language input meant
first closing a gap every earlier phase had explicitly deferred: nothing
in this codebase turned a question into an executed result.
`docs/planner-tool-schemas.md` said as much outright -- `ToolSchema.returns`
exists "for the validator and for whoever wires up real dispatch in
Tasks 7.3/8.x" -- and `generate_answer.py`'s own docstring: "Phase 8's
workflow engine is what will actually execute a Plan and produce these
for real." Neither task ever did. This is that wiring, confirmed with
the project owner before starting given its size: a new Python dispatch
module, a new backend resource, and the Ask Earth page itself.

## The real pipeline

```text
question
  -> generate_plan (Task 7.3, Gemini, structured output)
  -> validate_plan_or_raise (Task 7.2 -- generate_plan already calls
     this; an invalid plan never reaches dispatch)
  -> execute_plan (new: query/dispatch.py)
  -> generate_answer (Task 7.4, Gemini, grounded only in real outputs)
```

`query/run_ask_earth.py`'s `run_ask_earth(payload, client, backend)` is
the whole thing, mirroring `run_analysis.py`/`run_forecast.py`'s own
shape (real dependencies as parameters, no hidden global state).
`scripts/query/run_ask_earth_cli.py` is the thin stdin/stdout wrapper
`PythonEarthQueryRunner` (below) shells out to, exactly like
`run_analysis_cli.py`/`run_forecast_cli.py` already are.

## Real dispatch: every tool mapped to what already exists

`query/dispatch.py`'s `execute_plan` runs a validated `Plan`'s steps in
dependency order, resolving `$step_id.field` references against earlier
steps' real outputs (Task 7.2's validator already proved every such
reference is well-formed; this only substitutes). A step whose
dependency failed is never attempted -- `StepFailed` names every
failure, never a partial, silently-guessed answer.

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

Two of these needed real engineering, not just a function call:

- **`get_data`'s record count is filtered by region, not just by time.**
  The first version counted every observation in the time window
  regardless of the requested region (`len(observations)`); fixed to use
  `query.statistics.count`, the same region-aware count
  `calculate_statistics` itself uses, so `get_data` and
  `calculate_statistics` agree on how much data backs a region.
  Similarly, `ERA5History.for_cutoff` returns every grid cell in its
  lookback window with no region filter at all (it is built for the
  forecast pipeline, which always wants the whole California grid); this
  dispatcher filters those records to the requested bbox itself.
- **`run_forecast`/`get_result_evidence` go through the real HTTP API,
  not a direct Python call.** A plan step could call
  `query.run_forecast.run_forecast(...)` directly and skip the network
  entirely, but that would bypass everything Tasks 6.5/6.6/13.3/13.5
  built: idempotency, retries, tracing, and -- most importantly --
  `ForecastRecovery`. Going through `POST /forecasts` for real means a
  forecast step in a plan gets every one of those guarantees for free.

## Real dispatch found a real ordering bug in the Java worker

Verifying `execute_plan`'s use of the real `/forecasts` API against the
real running backend (`EarthQueryIntegrationTest` and manual runs) is
what turned up `ServerPort`'s own bug, described below -- proof that
dispatching for real, against the real system, surfaces things a
strictly mocked test would not have.

## The backend resource: `EarthQuery`

`POST /queries` / `GET /queries/{id}` / `GET /queries/{id}/result` --
mirrors `AnalysisController`'s exact shape (Task 6.3-style Postgres
storage via `V6__earth_queries.sql`, synchronous: no queue, the request
thread blocks for `PythonEarthQueryRunner`'s one subprocess call).
`EarthQueryRequest` is a bare `{question}`, bounded the same way
`AnalysisRequest.question` already is (Task 13.4's `RequestShape`).
`POST /queries` is rate-limited (Task 13.4's `RateLimitFilter`, its own
`api.rate-limit.queries-per-minute`, default 20/min) since it starts a
real LLM call plus a whole plan's execution, the same reasoning already
applied to `/forecasts`/`/analyses`.

`PythonEarthQueryRunner` is modeled on `PythonForecastRunner`, not the
simpler `PythonAnalysisRunner`: a plan can include a `run_forecast` step
(the dispatcher's own polling can take up to
`Backend.max_wait_seconds`, 150 s) and `generate_map` can produce a
large `FeatureCollection`, so both the bounded wait
(`ask-earth.python.timeout-seconds`, default 180 s) and the threaded
stdout/stderr draining (avoiding the OS-pipe-buffer deadlock Task 6.6
already found) apply here too.

### `ServerPort`, and the bug it found

The Python subprocess calls back into this same running backend for a
plan's `run_forecast`/`get_result_evidence` steps, so it needs that
backend's own real, bound port -- unknowable at construction time
(`@Value("${server.port}")` is `0` under
`@SpringBootTest(webEnvironment = RANDOM_PORT)`), so `ServerPort`
listens for Boot's own `WebServerInitializedEvent` and is read at
request time instead.

Task 13.4 gave the app a separate `management.server.port`, which means
Boot starts *two* embedded web servers, each firing its own
`WebServerInitializedEvent`. `EarthQueryIntegrationTest` -- the real
app, not a mock -- caught this immediately: without filtering, whichever
server's event fired second silently won, and the subprocess sometimes
got handed the *management* port instead of the real one.
`WebServerApplicationContext.getServerNamespace()` is Boot's own way to
tell the two apart (`null`/`""` for the main server, `"management"` for
the other); `ServerPort` now ignores the management one.

## The Ask Earth page

`AskEarthForm` (natural-language input, submit, recent queries) plus
`App.tsx`'s own loading/error/success handling, calling
`createEarthQuery`/`getEarthQueryResult` (`api/client.ts`) --
synchronous, matching `POST /queries` itself: await, then fetch the
result, exactly like the existing `createAnalysis`/`getAnalysisResult`
pair. Recent queries persist in `localStorage`
(`ai-earth:recent-queries`, capped at 8, deduplicated, most recent
first) -- a per-browser convenience, wrapped in `try`/`catch` since
storage access can throw (private browsing, blocked site data) and
nothing else depends on it succeeding. Clicking a recent query fills the
input; it does not resubmit it.

This page **replaces** Task 2.8's structured Earth-analysis form
(`QueryForm`/`ResultView`/`RegionMap`) as `App.tsx`'s own rendered
content, matching Phase 14's own name, "final frontend product" --
PROJECT_BIBLE's product definition is natural-language-first, and the
structured form was always the interim Phase 2 UI, built before the
planner existed at all. The old components and their own tests are
untouched on disk (still compiling, still passing) since `POST
/analyses` is still a real, working, separately useful route; they are
simply no longer what `App.tsx` renders.

## Task 14.2: the result page

`EarthQueryResultView` replaces the placeholder result snippet Task 14.1
left in `App.tsx` with the handbook's full list -- answer, map, numbers,
time, region, evidence -- rendered per fact (a plan can produce more than
one, e.g. a count alongside a forecast). `RegionMap` (Task 2.8) is reused
as-is: it only ever needed a bbox and a label, both of which a fact's own
`Evidence` already carries, so nothing about it changed.

Each fact's `result` is duck-typed by shape, mirroring `ResultView`'s own
existing pattern (`CountResult`/`DailyAggregateResult`/
`WeeklyAggregateResult`/`MapResult`), extended with the two shapes only
this pipeline produces: `DatasetReference` (`get_data`: source, product,
record count, provenance) and `ForecastJobReference` (`run_forecast`:
just `{forecast_id, status}` -- `docs/forecast-api-contract.md` locks
that a forecast job is created, not computed, here). Region/time/evidence
are rendered only when a fact carries its own `Evidence`
(`calculate_statistics`/`generate_map`); `get_data`/`run_forecast` facts
have none of their own (a forecast's evidence needs a separate
`get_result_evidence` step in the same plan), so those sections are
simply absent for them rather than showing an empty or fabricated one.

A `run_forecast` fact deliberately shows only the job reference, not a
risk grid -- that grid is Task 14.3's own forecast map, which needs
fields (legend, forecast horizon, calibration) this general result view
does not carry.

## Task 14.3: the forecast map

`ForecastMap` (`frontend/src/components/ForecastMap.tsx`) renders the
real `GET /forecasts/{id}/result` shape -- confirmed against the actual
current code, not just `docs/forecast-api-contract.md`'s prose, since
the doc's own illustrative JSON block reads as a flattened
`FeatureCollection` while the real `forecast_result_to_dict`
(`ml/.../query/forecast_result.py`) nests it under a top-level `grid`
key alongside `model_version`, `data_cutoff`, `forecast_window`,
`calibration`, and `evidence`; the component is written against that
real nesting.

It covers every field the handbook lists for this task: the California
grid (one coloured `<rect>` per feature, projected against the same
reference bbox `RegionMap` already uses so the two read at the same
scale), each cell's real `probability`, a scale legend, the forecast
horizon (`forecast_window`), the data cutoff, the model version, and
the calibration table plus the forecast's own evidence.

Colour follows the dataviz skill's procedure: probability is a
magnitude, not an identity, so it gets the skill's validated sequential
"blue" ramp (`references/palette.md`, steps 100 through 700) quantised
into 7 bins -- the unmodified reference instance, so no re-validation
was needed. Domain is the *grid's own* real min/max probability, not a
fixed [0, 1] range, labelled on the legend, so the colour spread stays
visible even though real wildfire-risk probabilities cluster near zero.
Every cell also carries a native SVG `<title>` (its tile ID and
probability as a hover tooltip) and a full sortable table view of every
cell folds under a `<details>` toggle -- the accessibility non-negotiable
that identity/value is never colour-alone, satisfied here by the real
numbers being present in text form too, not just implied by hue.

This component is intentionally standalone: it takes an already-`
SUCCEEDED` forecast's `ForecastResult` as a prop and renders it, the
same way `RegionMap` only ever needed a bbox and a label. Fetching a
forecast by ID and deciding *when* to show this component --
PENDING/RUNNING/FAILED handling -- is Task 14.4's "real job-status UI";
wiring it into a `run_forecast` fact on the result page is that task's
job too, once there is a real status to gate it on. `getForecastResult`
(`api/client.ts`) exists now, mirroring `getAnalysisResult`/
`getEarthQueryResult`, but nothing calls it yet.

## Task 14.4: the real job-status UI

`ForecastPanel` (`frontend/src/components/ForecastPanel.tsx`) is a new,
second section on the page, alongside Ask Earth -- not a further
wiring of Ask Earth's own `run_forecast` fact. That distinction is
deliberate: `query/dispatch.py`'s `dispatch_run_forecast` already polls
`POST /forecasts` to a terminal status *server-side* before a
`/queries` response is ever sent (see "Real dispatch" above), so by the
time a `ForecastJobReference` fact reaches the frontend it is always
already terminal -- there is no in-progress state left to show. A
genuine queued/running/completed/failed UI needs a job the browser
itself watches while it is still in flight, which means the *direct*,
asynchronous `POST /forecasts` path, submitted through a new
`ForecastRequestForm` (region + cutoff only, no operation or time
range -- the same region-kind fieldset `QueryForm` already established).

`ForecastPanel` submits the job, then polls `GET /forecasts/{id}`
(`getForecastStatus`, `api/client.ts`) every 2s (matching
`dispatch_run_forecast`'s own `poll_interval_seconds=1.0` order of
magnitude, not hammering the endpoint) until the real
`Forecast.Status` reaches a terminal value, then fetches
`GET /forecasts/{id}/result` and renders `ForecastMap` (Task 14.3) on
success or the real backend error message on failure. Never a
fabricated progress percentage: the handbook's own four states
(queued/running/completed/failed) are a direct, honest fold of the six
real backend values -- PENDING and RETRYING both read as "queued" (both
are waiting for an attempt, not making one), CANCELLED folds into
"failed" (a non-success terminal state; unreachable today per
`Forecast.java`'s own comment, since no cancel endpoint exists) -- and
the real backend status string is always shown alongside the folded
label, never hidden behind it. Status is rendered as a shape (not just
a colour) plus a text label plus the raw backend value, using the
dataviz skill's reserved status palette (good/warning/serious/critical),
so meaning is never colour-alone.

**A real bug this caught:** testing `ForecastPanel` against the actual
running backend (not just the mocked-client unit tests) found that
every Forecast response field is serialized as `snake_case`
(`spring.jackson.property-naming-strategy=SNAKE_CASE`,
`application.properties`) -- `POST /forecasts` really returns
`{"forecast_id": ..., "status": ...}`, not the `forecastId` this task's
first draft assumed straight from `ForecastSummaryResponse`'s own Java
field name. `ForecastResultResponse` has the same field. Every other
response type in this codebase (`EarthQuerySummaryResponse`,
`ResultResponse`, ...) happens to use single-word field names
(`id`, `status`, `result`) where snake_case and camelCase are
identical, which is exactly why this had gone unnoticed: nothing before
this task ever exercised a multi-word Java record field's real wire
name. Fixed by renaming `ForecastSummary`/`ForecastResultResponse`'s own
`forecastId` to `forecast_id`, matching this codebase's established
convention of typing a response exactly as its wire shape (`Evidence`,
`CalibrationBin`, etc. are already all snake_case), not camel-casing it
on the way in.

## What this task does not do

- **`ForecastPanel` is a separate section, not Ask Earth's own
  `run_forecast` fact wired up.** As above, Ask Earth's embedded
  forecast step is already resolved by the time a `/queries` response
  exists, so there is no separate status UI to add there; a
  `run_forecast` fact still only ever shows its job reference
  (Task 14.2), unchanged by this task.
- **Nothing here changes `WorkflowExecutor`.** `execute_plan` is its own
  simple, sequential, non-persistent executor purpose-built for one
  synchronous Ask Earth request; `WorkflowExecutor` (Task 8.3) still has
  no real caller, unchanged by this task.
- **The malformed-input properties Task 13.5 already proved** (a corrupt
  FIRMS row fails cleanly, the service stays up) are not re-proven here;
  `execute_plan` reuses `run_analysis`/`POST /forecasts` exactly, so
  those same guarantees carry over rather than needing a second test.

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
EarthQueryControllerTest                 9  mirrors AnalysisControllerTest exactly
PythonEarthQueryRunnerTest                5  mirrors PythonForecastRunnerTest; proves the
                                             subprocess really receives ASK_EARTH_BACKEND_BASE_URL
EarthQueryIntegrationTest                 3  the real app, real Postgres, the real
                                             ServerPort event wiring (not the unit tests'
                                             manual setForTest) -- this is what caught the
                                             management-port bug
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
ForecastMap.test.tsx                      6  one coloured cell per real grid feature with
                                             a hover title; model version/data cutoff/
                                             forecast window shown; legend spans the
                                             grid's own real min/max probability;
                                             calibration table and full per-cell table
                                             view both present; the forecast's own
                                             evidence shown
ForecastRequestForm.test.tsx               4  named/bbox/coordinates region submission;
                                             cutoff read as UTC; disabled while a job
                                             is already in flight
ForecastPanel.test.tsx                     4  real initial status shown right after
                                             submit, form disabled meanwhile; the real
                                             result rendered once the backend reports
                                             SUCCEEDED; the real backend error shown on
                                             FAILED, not a fabricated one; the real
                                             submission error shown when the job
                                             cannot even be created
```

A real, live run against the actual Gemini API and the actual FIRMS
history (not a test assertion) also confirmed the pipeline end to end
twice, independently: "How many fires occurred in California between
August 1 and August 5, 2024?" produced a real plan
(`calculate_statistics`, region `california`, the model's own reading of
the date range), a real count against `data/raw/firms/history`, and a
grounded answer -- one run's answer plainly noted that the plan's own
half-open time window did not exactly match the question's literal
wording, rather than silently asserting an exact-sounding number, which
is precisely the "never fabricate" property PROJECT_BIBLE locks.

Full backend suite after Task 14.1: **173 tests, 0 failures** (155
before). Full `ml` suite: **528 -> 545 tests** (17 new, dispatch.py/
run_ask_earth.py), still 0 failures, 2 skipped (the pre-existing
real-model forecast tests, unrelated to this task). Frontend after Task
14.1: **27 tests, 0 failures** (19 before, +8 new for `AskEarthForm`,
`App.test.tsx` rewritten for the new flow rather than added to). Frontend
after Task 14.2: **35 tests, 0 failures** (+8 new for
`EarthQueryResultView`). Frontend after Task 14.3: **41 tests, 0
failures** (+6 new for `ForecastMap`). Frontend after Task 14.4: **49
tests, 0 failures** (+4 new for `ForecastRequestForm`, +4 new for
`ForecastPanel`).

## Task 14.5: browser end-to-end flow verification

This environment has no browser-automation tool, so a literal
click-through of a rendered browser page was not possible. Instead,
both flows were driven at the API layer with the exact requests
`client.ts` itself issues (same URLs, methods, and bodies a browser's
`fetch()` calls would send) against a real, freshly built backend and
the real Docker Compose infra (Postgres/Redis/MinIO) -- not mocks, not
a replay of earlier canned responses. This is a genuine substitute for
what a browser would do, short of literally rendering pixels; it does
not exercise React's own rendering, so a rendering-only bug (a typo in
JSX, a missed prop) would not be caught by it the way the component
tests already are.

**Found along the way:** `curl http://localhost:8080/readyz` returned a
healthy response before this task started, but `POST /queries` 404'd
against it -- that port was actually being served by a stale kind
Kubernetes cluster's `ai-earth-backend` image (Docker Desktop/WSL
forwarding it, not a Maven process), built before Task 14.1 added
`EarthQueryController`. A fresh backend was started for real
(`./mvnw spring-boot:run` with `SERVER_PORT=8090`/`MANAGEMENT_PORT=8091`
to avoid that occupied port) against the same Docker Compose stack, and
every check below ran against that real, current build.

### Earth question -> planner -> validated workflow -> computation -> result -> map -> evidence

`POST /queries {"question": "Show me a map of wildfire counts across
the Bay Area in August 2024"}` against the real Gemini API produced a
real plan (`generate_map`, region `bay area`, time range 2024-08-01 to
2024-09-01 -- the model's own reading of "August 2024"), which passed
real plan validation, then real dispatch executed it against the real
FIRMS history and returned a genuine `FeatureCollection` fact: one
polygon (the Bay Area's real bbox), `properties.value: 245`,
`units: "fire_count"`. The grounded answer text ("The Bay Area recorded
245 wildfire counts during August 2024 (computed)...") and the fact's
own `evidence` (`dataset: "NASA_FIRMS:VIIRS_SNPP_SP"`, the real
`region_bbox`, `period_start`/`period_end`, `query_parameters`) matched
`EarthQueryResultView.tsx`'s expected shape field-for-field: the
`isMapResult` branch would render `"bay_area: 245 fire_count"`, and the
evidence section would show the real dataset, region, and time range --
exactly the "map" and "evidence" the handbook asks this flow to reach.

### forecast question -> job -> status -> prediction -> uncertainty -> evidence

`POST /forecasts` for the same region created a real job
(`{"forecast_id": ..., "status": "PENDING"}`); polling
`GET /forecasts/{id}` observed the real, live transition
PENDING -> RUNNING -> FAILED (not simulated -- `ForecastWorker` picked
the job up from the real Redis queue and ran it), and
`GET /forecasts/{id}/result` returned the real
`422 {"error": "no trained production model at ml/artifacts/
production_model_v1 -- run scripts/models/train_production_model.py
first"}` -- exactly the shape `ForecastPanel`'s own error handling
expects and renders as an alert.

**Known gap, out of this task's scope by the project owner's own
choice:** this environment has no trained `production_model_v1` (its
own build needs `scripts/forecast/build_historical_dataset.py` over the
full 2019-2024 FIRMS/ERA5 history first, an unscoped, potentially
long-running job), so a genuine *SUCCEEDED* prediction -- real
probabilities and a real calibration ("uncertainty") table -- was not
exercised live here. That response shape was already verified against
the real `forecast_result_to_dict`/`cell_to_feature` code in Task
14.3's own research, and `ForecastMap`/`ForecastPanel`'s handling of it
is covered by their own component tests; only the live numbers are
unverified, not the contract.
