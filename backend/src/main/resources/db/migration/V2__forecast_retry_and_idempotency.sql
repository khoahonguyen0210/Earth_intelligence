-- Retry bookkeeping and
-- idempotency for the forecast job flow. See
-- docs/forecast-retry-and-idempotency.md.

ALTER TABLE forecasts ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE forecasts ADD COLUMN idempotency_key VARCHAR(255);

-- Partial unique index: many forecasts have no idempotency key (NULL is
-- never considered equal to NULL by a unique index), but a given key can
-- back at most one forecast row -- the "same idempotency key ->
-- one logical job".
CREATE UNIQUE INDEX idx_forecasts_idempotency_key ON forecasts (idempotency_key) WHERE idempotency_key IS NOT NULL;
