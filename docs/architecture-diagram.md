# Architecture Diagram

This diagram shows the request path, from React to the Earth data
sources. Each stage points to the code and the document that define it.

## Request path

```text
   React + TypeScript (frontend/src)
             |
             |  fetch(): AskEarthForm / ForecastRequestForm
             v
   Java 21 / Spring Boot  (backend/src/main/java)
             |
             |  POST /queries
             v
   AI Planner  (ml/.../planner/generate_plan.py)
             |
             |  question in plain English -> structured Plan (Gemini,
             |  a fixed set of tools; never free-form code)
             v
   Validator  (ml/.../planner/validator.py)
             |
             |  validate_plan_or_raise: rejects an invalid Plan before
             |  any step runs; a more convincing plan from the LLM
             |  cannot get past this check
             v
   Workflow  (ml/.../query/dispatch.py :: execute_plan)
             |
             |  runs the validated Plan's steps in dependency order,
             |  passing in each earlier step's output
             v
        +----+----------------------------------+
        |                                        |
  sync steps                              run_forecast step
  (calculate_statistics,                        |
   generate_map,                                v
   get_data)                              Redis  (ForecastQueue)
        |                                        |
        |                                        v
        |                              Python Workers
        |                              (ForecastWorker, a loop in the
        |                               backend; PythonForecastRunner
        |                               starts the subprocess)
        |                                        |
        +--------------------+-------------------+
                              v
                PostGIS / Object Storage
              (Postgres for stored records;
               MinIO/S3 for artifacts)
                              |
                              v
                       Earth Data Sources
              (NASA FIRMS, ERA5-Land, Copernicus DEM,
               ESA WorldCover; see README "Data")
```

## Where each stage is defined

```text
React + TypeScript        frontend/src: AskEarthForm, ForecastPanel,
                          ForecastMap, EarthQueryResultView
                          (docs/ask-earth.md)

Spring Boot               EarthQueryController and ForecastController:
                          POST /queries (synchronous), POST /forecasts
                          (async job). docs/forecast-api-contract.md

AI Planner                generate_plan(question, client): one Gemini
                          call that returns a structured Plan.
                          docs/natural-language-planner.md

Validator                 validate_plan_or_raise: every step's tool,
                          inputs and $step_id.field references are
                          checked before dispatch. docs/plan-validator.md

Workflow                  execute_plan (query/dispatch.py) for the
                          synchronous Ask Earth path. WorkflowExecutor
                          (workflow/) is the DAG executor used by the
                          partial-failure test in the reliability suite;
                          it has no route of its own yet.
                          docs/workflow-execution.md,
                          docs/workflow-dag-schema.md

Redis                     ForecastQueue: a list of bare ids, taken with
                          RPOP by the worker loop. PostGIS holds the
                          true state; Redis is only a hint of what to
                          run next. docs/forecast-async-jobs.md

Python Workers            ForecastWorker claims a job (one atomic
                          conditional UPDATE), then PythonForecastRunner
                          starts scripts/query/run_forecast_cli.py as a
                          subprocess: a process boundary, not a network
                          call. docs/forecast-retry-and-idempotency.md

PostGIS / Object Storage  schema migrated by Flyway (Forecast and
                          EarthQuery rows); S3ObjectStoreTest checks
                          put, get, exists and delete on MinIO and AWS S3.
                          docs/persistence-schema.md,
                          docs/object-storage-contract.md

Earth Data Sources        NASA FIRMS, ERA5-Land, Copernicus DEM GLO-30,
                          ESA WorldCover; see README "Data" and each
                          source's input-contract document.
```

## Other views

The Architecture section of `README.md` gives a shorter overview for a
first-time reader. This document gives the detailed request path, stage
by stage, with the file and document behind each stage.
