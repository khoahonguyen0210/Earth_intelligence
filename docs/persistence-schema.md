# Persistence Schema

This document defines the PostgreSQL/PostGIS schema. The Redis async
jobs and the retry, timeout and idempotency work use this schema and do
not redefine it.

`infra/docker/docker-compose.yml` runs `postgis/postgis` with the
credentials in `application.properties` (`ai_earth`/`ai_earth`/
`ai_earth_dev`, port 5432). Run `docker compose up -d` from
`infra/docker/` before running the backend or its tests.
`BackendApplicationTests` needs a live datasource: the old
`DataSourceAutoConfiguration` exclusion is gone, because JPA
repositories now exist and require one. Flyway applies the schema at
startup (`backend/src/main/resources/db/migration/V1__initial_schema.sql`);
Hibernate `ddl-auto` stays at `validate`.

## The eight tables

Eight kinds of data must be stored. All eight tables exist, with correct
types and indexes. Three have Java code that reads and writes them:

```text
analyses    USED  AnalysisEntity/AnalysisJpaRepository, behind
                  AnalysisStore (a job and result flow)
forecasts   USED  ForecastEntity/ForecastJpaRepository, behind
                  ForecastStore (a job and result flow)
regions     USED  RegionStore (com.example.backend.region), a plain
                  JdbcTemplate upsert, not a JPA entity (see below)

jobs        schema only
grid_cells  schema only
workflows   schema only
datasets    schema only
models      schema only
evidence    schema only
```

## Why only three are used

`analyses`, `forecasts` and `regions` are the tables that tested code
writes today. `AnalysisController`, and `ForecastController` with
`ForecastWorker`, each create a request, status and result record per
HTTP call. `RegionStore` records every region that these controllers
(and `EarthQueryController`) resolved.

`query.evidence.build_evidence` already adds `region_kind`,
`region_label` and `region_bbox` to the evidence of every analysis,
the `result.evidence` of every forecast, and the `evidence` of every Ask
Earth fact. `RegionStore.recordFrom` reads this from each successful
result and upserts one row per distinct region (`ON CONFLICT (id) DO
NOTHING`, keyed by kind and label, or by kind and bounding box when
there is no label). Repeated requests for "california" do not grow the
table; they find the same row. The geometry is a PostGIS rectangle
built on the server with `ST_MakeEnvelope`, in the same way that
`query.region.normalize_region` turns every region kind into a bounding
box polygon in Python. No JTS or Hibernate Spatial dependency was added,
because a plain `JdbcTemplate` upsert covers the one write this table
needs.

The other five have no caller yet:

- `jobs` is the general async-job record for the Redis worker
  (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `RETRYING`, `CANCELLED`,
  see `docs/forecast-api-contract.md`). `analyses` and `forecasts`
  already have their own id, status and error, and are not rows in this
  table.
- `grid_cells` would store `data.grid.build_california_grid()`, but no
  Java code reads or writes the grid. Python creates and uses it
  (`scripts/data/generate_grid.py`, `data/processed/grid/`, which git
  ignores and which is rebuilt on demand, see
  `docs/california-grid-contract.md`).
- `workflows`, `datasets` and `models` have no runtime object in either
  codebase yet. Datasets and models are files under `ml/artifacts/`, not
  database rows, and no part of the project implements a named workflow
  pipeline yet.
- Evidence is already stored inside `analyses.evidence` and
  `forecasts.result` (see `docs/forecast-api-contract.md`; a forecast's
  evidence is nested in its result). The separate table is for future
  queries across both; nothing writes to it today.

Writing JPA entities, repositories and app code for tables that nothing
calls would add untested code with no use, which the project avoids
elsewhere too. The schema for the other five is fixed now, so later work
can connect a caller to each one without a migration.

## Spatial indexes

`regions.geometry`, `grid_cells.geometry` and `grid_cells.centroid` are
PostGIS `geometry` columns (SRID 4326, like every bounding box in the
project), each with a `GIST` index. This is the standard PostGIS index
for containment and intersection queries (`ST_Within`, `ST_Intersects`),
which a future "which region or cell contains this point" lookup would
use.

## Out of scope

The Redis job states are covered in `docs/forecast-async-jobs.md`. Which
Java code will read and write `regions`, `grid_cells`, `workflows`,
`datasets`, `models` and `evidence`, and in what shape, is left to the
work that gives each table its first caller. This document fixes only
the column-level contract that such work builds on.
