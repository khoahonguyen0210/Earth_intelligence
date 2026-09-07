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

## What this task does not do

- **The result page is Task 14.2's job.** `App.tsx` shows the grounded
  answer and the tagged facts behind it (enough to prove the pipeline is
  real); the fuller layout the handbook lists for 14.2 -- map, numbers,
  time, region, evidence -- is that task's own work, not duplicated here.
- **No job-status UI.** `POST /queries` is synchronous; Task 14.4's "real
  job-status UI" is about the forecast job queue, which a plan's
  `run_forecast` step already goes through for real without exposing its
  own separate status polling to this page.
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

Full backend suite after this task: **173 tests, 0 failures** (155
before). Full `ml` suite: **528 -> 545 tests** (17 new, dispatch.py/
run_ask_earth.py), still 0 failures, 2 skipped (the pre-existing
real-model forecast tests, unrelated to this task). Frontend: **27
tests, 0 failures** (19 before, +8 new for `AskEarthForm`, `App.test.tsx`
rewritten for the new flow rather than added to).
