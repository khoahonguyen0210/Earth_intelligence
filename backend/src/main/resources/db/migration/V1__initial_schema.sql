-- Task 6.3 (Execution Handbook Phase 6): the persistence schema for
-- everything the handbook lists -- regions, grid cells, jobs, workflows,
-- datasets, models, forecast metadata, evidence. See
-- docs/persistence-schema.md for which of these tables an actual Java
-- read/write path exists for today, and which are schema only, reserved
-- for a later task.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Generic async-job envelope. Task 6.5's Redis worker will drive status
-- transitions on this table once it exists; for now nothing writes to it
-- (analyses/forecasts below already carry their own id/status/error and
-- are the two real request/result flows Tasks 2.7/6.2 built).
CREATE TABLE jobs (
    id VARCHAR(255) PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    error TEXT
);

CREATE INDEX idx_jobs_job_type_status ON jobs (job_type, status);

-- Earth-analysis requests/results (Task 2.7), now durable instead of the
-- in-memory AnalysisStore.
CREATE TABLE analyses (
    id VARCHAR(255) PRIMARY KEY,
    request JSONB NOT NULL,
    status TEXT NOT NULL,
    result JSONB,
    evidence JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

-- Forecast requests/results (Tasks 6.1/6.2), now durable instead of the
-- in-memory ForecastStore. Evidence lives nested inside result (per
-- docs/forecast-api-contract.md), not a separate column here.
CREATE TABLE forecasts (
    id VARCHAR(255) PRIMARY KEY,
    request JSONB NOT NULL,
    status TEXT NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

-- The named/bbox/coordinate regions a query can resolve to (Task 2.2's
-- NormalizedRegion), persisted. Schema only -- see
-- docs/persistence-schema.md.
CREATE TABLE regions (
    id VARCHAR(255) PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT,
    west DOUBLE PRECISION NOT NULL,
    south DOUBLE PRECISION NOT NULL,
    east DOUBLE PRECISION NOT NULL,
    north DOUBLE PRECISION NOT NULL,
    geometry GEOMETRY(POLYGON, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_regions_geometry ON regions USING GIST (geometry);

-- The locked California grid (data.grid.build_california_grid), persisted.
-- Schema only -- see docs/persistence-schema.md.
CREATE TABLE grid_cells (
    tile_id TEXT PRIMARY KEY,
    grid_version TEXT NOT NULL,
    lat_index INTEGER NOT NULL,
    lon_index INTEGER NOT NULL,
    min_lon DOUBLE PRECISION NOT NULL,
    min_lat DOUBLE PRECISION NOT NULL,
    max_lon DOUBLE PRECISION NOT NULL,
    max_lat DOUBLE PRECISION NOT NULL,
    centroid GEOMETRY(POINT, 4326) NOT NULL,
    geometry GEOMETRY(POLYGON, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_grid_cells_geometry ON grid_cells USING GIST (geometry);
CREATE INDEX idx_grid_cells_centroid ON grid_cells USING GIST (centroid);
CREATE INDEX idx_grid_cells_grid_version ON grid_cells (grid_version);

-- Named orchestration pipelines (e.g. a scheduled daily forecast run).
-- Schema only -- see docs/persistence-schema.md.
CREATE TABLE workflows (
    id VARCHAR(255) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

-- forecast.build_dataset.DatasetManifest, persisted. Schema only -- see
-- docs/persistence-schema.md.
CREATE TABLE datasets (
    id VARCHAR(255) PRIMARY KEY,
    dataset_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    row_counts JSONB NOT NULL,
    positive_rates JSONB NOT NULL,
    split_dates JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL
);

-- Frozen model artifacts (models.calibration.MODEL_VERSION and friends).
-- Schema only -- see docs/persistence-schema.md.
CREATE TABLE models (
    id VARCHAR(255) PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    config JSONB NOT NULL,
    best_iteration INTEGER,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX idx_models_name_version ON models (model_name, model_version);

-- query.evidence.Evidence, persisted as its own queryable table (in
-- addition to living embedded in analyses.evidence / forecasts.result).
-- Schema only -- see docs/persistence-schema.md.
CREATE TABLE evidence (
    id VARCHAR(255) PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id VARCHAR(255),
    dataset TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    region_kind TEXT NOT NULL,
    region_label TEXT,
    region_west DOUBLE PRECISION NOT NULL,
    region_south DOUBLE PRECISION NOT NULL,
    region_east DOUBLE PRECISION NOT NULL,
    region_north DOUBLE PRECISION NOT NULL,
    query_parameters JSONB NOT NULL,
    processing_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_evidence_source ON evidence (source_type, source_id);
