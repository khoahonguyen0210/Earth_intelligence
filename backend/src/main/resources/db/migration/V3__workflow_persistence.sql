-- Gives `jobs`/`workflows`
-- (schema only until now) their first real read/write path -- the
-- WorkflowNode/Workflow shape, persisted. See
-- docs/workflow-persistence.md.
--
-- `jobs.id` was already the primary key for a single global async job
-- (the original schema); a WorkflowNode's own task_id (e.g. "get_data") is only
-- unique *within* one workflow, not globally -- the same task_id
-- legitimately appears in every run of the same workflow shape. A new
-- task_id column plus a per-workflow unique index keeps that distinction
-- explicit rather than overloading `id` to mean two different things.
ALTER TABLE jobs ADD COLUMN task_id VARCHAR(255);
ALTER TABLE jobs ADD COLUMN workflow_id VARCHAR(255) REFERENCES workflows(id);
ALTER TABLE jobs ADD COLUMN dependencies JSONB NOT NULL DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0;
-- TEXT, not JSONB: WorkflowNode's own docs say inputRef/
-- outputRef are opaque reference strings (a JSON blob, an object-storage
-- key, a $step_id.field reference), not always valid JSON on their own.
ALTER TABLE jobs ADD COLUMN input_ref TEXT;
ALTER TABLE jobs ADD COLUMN output_ref TEXT;

CREATE UNIQUE INDEX idx_jobs_workflow_task ON jobs (workflow_id, task_id) WHERE workflow_id IS NOT NULL;
