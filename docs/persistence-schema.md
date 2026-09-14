# Persistence Schema — LOCKED

This document freezes the PostgreSQL/PostGIS persistence schema per Task
6.3 of the Execution Handbook. It is not a brainstorming document. Tasks
6.5 (Redis async jobs) and 6.6 (retry/timeout/idempotency) build against
this schema rather than redefining it.

Infrastructure: `infra/docker/docker-compose.yml` runs `postgis/postgis`
on the exact credentials already in `application.properties`
(`ai_earth`/`ai_earth`/`ai_earth_dev`, port 5432). Run
`docker compose up -d` from `infra/docker/` before running the backend or
its tests — since this task, `BackendApplicationTests` genuinely needs a
live datasource (the earlier `DataSourceAutoConfiguration` exclusion is
gone; JPA repositories now exist and require it). Schema is applied by
Flyway (`backend/src/main/resources/db/migration/V1__initial_schema.sql`)
on startup, not by Hibernate `ddl-auto` (still `validate`).

## The eight tables

The handbook lists eight things to persist. All eight exist as real,
migrated tables with correct types and indexes. Three have a Java
read/write path wired up today:

```text
analyses    REAL  -- AnalysisEntity/AnalysisJpaRepository, backing
                     AnalysisStore (Task 2.7's job/result flow)
forecasts   REAL  -- ForecastEntity/ForecastJpaRepository, backing
                     ForecastStore (Task 6.2's job/result flow)
regions     REAL  -- RegionStore (com.example.backend.region), a plain
                     JdbcTemplate upsert, not a JPA entity -- see below

jobs        schema only
grid_cells  schema only
workflows   schema only
datasets    schema only
models      schema only
evidence    schema only
```

## Why only three are wired

`analyses`, `forecasts`, and now `regions` are the tables with a real,
already-tested producer today. Task 2.7's `AnalysisController` and Task
6.2's `ForecastController`/`ForecastWorker` each create a genuine
request/status/result record per HTTP call, and `RegionStore` records
every region those (plus Task 14.1's `EarthQueryController`) actually
resolved: `query.evidence.build_evidence` already attaches
`region_kind`/`region_label`/`region_bbox` to every analysis's evidence,
every forecast's `result.evidence`, and every Ask Earth fact's own
`evidence`; `RegionStore.recordFrom` reads that same shape off each
success and upserts one row per distinct region (`ON CONFLICT (id) DO
NOTHING`, keyed by kind+label, or kind+bbox when there is no label) --
repeat requests for "california" never grow the table, they just confirm
the same row. Geometry is a PostGIS rectangle built server-side with
`ST_MakeEnvelope`, matching how `query.region.normalize_region` already
turns every region kind into a bbox polygon on the Python side; no JTS/
Hibernate Spatial dependency was added for this, since a plain
`JdbcTemplate` upsert covers the one write path this table needs.

The other five have no real caller yet:

- `jobs` is the generic async-job envelope Task 6.5's Redis worker will
  actually drive (`PENDING`/`RUNNING`/`SUCCEEDED`/`FAILED`/`RETRYING`/
  `CANCELLED`, per `docs/forecast-api-contract.md`). `analyses`/
  `forecasts` already carry their own id/status/error and are not rows in
  this table.
- `grid_cells` would back `data.grid.build_california_grid()`, but
  nothing in Java reads or writes the grid; it is generated and consumed
  entirely in Python today (`scripts/data/generate_grid.py`,
  `data/processed/grid/` — gitignored and regenerated on demand per
  `docs/california-grid-contract.md`).
- `workflows`, `datasets`, `models` have no equivalent runtime object in
  either codebase yet — `datasets`/`models` currently live as files under
  `ml/artifacts/`, not database rows, and `workflows` names a concept
  (a named orchestration pipeline) nothing in the project implements yet.
- `evidence` already lives embedded in `analyses.evidence` and
  `forecasts.result` (per `docs/forecast-api-contract.md`, evidence is
  nested inside a forecast's result, not a sibling). The standalone table
  exists for future direct evidence queries across both, not because
  anything writes to it today.

Building JPA entities/repositories/app code around a table nothing calls
would be exactly the kind of speculative, untested abstraction this
project avoids elsewhere (Phase 0: "Do not add speculative services").
The schema for the remaining five is real and locked now, precisely so a
later task can wire a real caller against each one without a migration
change.

## Spatial indexes

`regions.geometry` and `grid_cells.geometry`/`grid_cells.centroid` are
native PostGIS `geometry` columns (SRID 4326, matching every bbox already
used project-wide), each with a `GIST` index — the standard PostGIS index
type for containment/intersection queries (`ST_Within`, `ST_Intersects`),
which is the actual query pattern a future "which region/cell contains
this point" lookup would use.

## What this document does not define

The Redis job-state machine is Task 6.5's job, not this one. Which Java
code eventually reads/writes `regions`/`grid_cells`/`workflows`/
`datasets`/`models`/`evidence`, and in what shape, is deferred to
whichever future task gives each one its first real caller — this
document only fixes the column-level contract those tasks build against.
