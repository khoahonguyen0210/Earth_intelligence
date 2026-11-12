ALTER TABLE forecasts ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE forecasts ADD COLUMN idempotency_key VARCHAR(255);

CREATE UNIQUE INDEX idx_forecasts_idempotency_key ON forecasts (idempotency_key) WHERE idempotency_key IS NOT NULL;
