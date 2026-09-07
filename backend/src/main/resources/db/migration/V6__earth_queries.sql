-- Task 14.1 (Execution Handbook Phase 14): the "Ask Earth" page's own
-- resource -- a natural-language question, the real plan the planner
-- produced, and the real grounded answer that came out of executing it.
-- See docs/ask-earth.md. Synchronous, like the analyses table (Task 6.3):
-- there is no queue, no worker, no retry state here -- POST /queries
-- blocks for the one real answer, the same way POST /analyses already
-- does.

CREATE TABLE earth_queries (
    id VARCHAR(255) PRIMARY KEY,
    request JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
