-- The W3C traceparent of the
-- span that submitted the forecast job, so the worker that later picks
-- the job up off the queue -- on another thread or another replica --
-- continues the submitting HTTP request's trace. See docs/tracing.md.
-- 55 characters is the whole version-00 header
-- (00-<32 hex trace id>-<16 hex span id>-<2 hex flags>). NULL for rows
-- written before tracing existed or while nothing was being traced; the
-- worker then starts a new trace for the job.

ALTER TABLE forecasts ADD COLUMN trace_parent VARCHAR(55);
