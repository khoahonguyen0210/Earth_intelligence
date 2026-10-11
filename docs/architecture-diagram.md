# Architecture Diagram — LOCKED

This document records the request-path architecture diagram. It is
not a brainstorming document. It shows the one request path in scope
— React through Earth Data — annotated with the real code and
locked doc that defines each stage, not a redrawing of anything new.

## The request path

```text
   React + TypeScript (frontend/src)
             |
             |  fetch() -- AskEarthForm / ForecastRequestForm
             v
   Java 21 / Spring Boot  (backend/src/main/java)
             |
             |  POST /queries
             v
   AI Planner  (ml/.../planner/generate_plan.py)
             |
             |  natural-language question -> structured Plan (Gemini,
             |  a fixed tool surface -- never free-form code)
             v
   Validator  (ml/.../planner/validator.py)
             |
             |  validate_plan_or_raise: rejects an invalid Plan before
             |  a single step executes -- the LLM cannot get past this
             |  gate by producing a more convincing-looking plan
             v
   Workflow  (ml/.../query/dispatch.py :: execute_plan)
             |
             |  runs the validated Plan's steps in dependency order,
             |  substituting each step's real prior output
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
        |                              (ForecastWorker, backend-side
        |                               loop; PythonForecastRunner
        |                               spawns the real subprocess)
        |                                        |
        +--------------------+-------------------+
                              v
                PostGIS / Object Storage
              (Postgres persistence; MinIO/S3
               for artifacts)
                              |
                              v
                       Earth Data Sources
              (NASA FIRMS, ERA5-Land, Copernicus DEM,
               ESA WorldCover -- see README "Data")
```

## Each stage, and where it's actually defined

```text
React + TypeScript        frontend/src -- AskEarthForm, ForecastPanel,
                           ForecastMap, EarthQueryResultView
                           (docs/ask-earth.md)

Spring Boot                EarthQueryController / ForecastController --
                           POST /queries (synchronous), POST /forecasts
                           (async job). docs/forecast-api-contract.md

AI Planner                 generate_plan(question, client): one real
                           Gemini call, structured-output Plan.
                           docs/natural-language-planner.md

Validator                  validate_plan_or_raise: every step's tool,
                           inputs, and $step_id.field references
                           checked before dispatch. docs/plan-validator.md

Workflow                   execute_plan (query/dispatch.py) for the
                           synchronous Ask Earth path; WorkflowExecutor
                           (workflow/) is the same DAG-execution engine
                           used by the reliability suite's partial-
                           failure proof, not yet wired to its own
                           route. docs/workflow-execution.md,
                           docs/workflow-dag-schema.md

Redis                      ForecastQueue: a bare-id list, RPOP'd by the
                           worker loop; PostGIS is the source of truth,
                           Redis only a hint of what to run next.
                           docs/forecast-async-jobs.md

Python Workers              ForecastWorker claims a job (one atomic
                           conditional UPDATE), then PythonForecastRunner
                           spawns the real scripts/query/run_forecast_cli.py
                           subprocess -- a process boundary, not a
                           network call. docs/forecast-retry-and-idempotency.md

PostGIS / Object Storage    Flyway-migrated schema (Forecast, EarthQuery
                           rows); S3ObjectStoreTest proves the real
                           MinIO/AWS S3 put/get/exists/delete wiring.
                           docs/persistence-schema.md,
                           docs/object-storage-contract.md

Earth Data Sources          NASA FIRMS, ERA5-Land, Copernicus DEM
                           GLO-30, ESA WorldCover -- see README "Data"
                           and each source's own input-contract doc.
```

## What this document does not define

A second, real diagram already exists at a different level of detail
in the project's architecture notes (the locked architecture this
project committed to before implementation) and in `README.md`'s own
Architecture section (a shorter version for a first-time reader). This
document is the one explicitly asked for here -- the request path,
stage by stage, each one pointing at the real file and locked doc that
proves it, rather than a fourth restatement of the same boxes.
