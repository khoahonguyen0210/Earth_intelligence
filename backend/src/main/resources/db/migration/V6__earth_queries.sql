CREATE TABLE earth_queries (
    id VARCHAR(255) PRIMARY KEY,
    request JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
