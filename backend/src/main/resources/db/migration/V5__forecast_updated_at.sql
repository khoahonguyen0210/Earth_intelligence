-- When a forecast row last
-- changed state, so ForecastRecovery can tell a job that is merely
-- waiting or running from one abandoned by a worker that died, or never
-- queued because Redis was down (docs/reliability-tests.md). Existing
-- rows take their creation time.

ALTER TABLE forecasts ADD COLUMN updated_at TIMESTAMPTZ;
UPDATE forecasts SET updated_at = created_at;
ALTER TABLE forecasts ALTER COLUMN updated_at SET NOT NULL;

-- The recovery sweep's two queries: by status, oldest first.
CREATE INDEX idx_forecasts_status_updated_at ON forecasts (status, updated_at);
