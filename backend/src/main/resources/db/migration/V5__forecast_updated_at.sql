ALTER TABLE forecasts ADD COLUMN updated_at TIMESTAMPTZ;
UPDATE forecasts SET updated_at = created_at;
ALTER TABLE forecasts ALTER COLUMN updated_at SET NOT NULL;

CREATE INDEX idx_forecasts_status_updated_at ON forecasts (status, updated_at);
