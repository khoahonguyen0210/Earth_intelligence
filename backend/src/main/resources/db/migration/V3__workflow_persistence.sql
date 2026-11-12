ALTER TABLE jobs ADD COLUMN task_id VARCHAR(255);
ALTER TABLE jobs ADD COLUMN workflow_id VARCHAR(255) REFERENCES workflows(id);
ALTER TABLE jobs ADD COLUMN dependencies JSONB NOT NULL DEFAULT '[]';
ALTER TABLE jobs ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN input_ref TEXT;
ALTER TABLE jobs ADD COLUMN output_ref TEXT;

CREATE UNIQUE INDEX idx_jobs_workflow_task ON jobs (workflow_id, task_id) WHERE workflow_id IS NOT NULL;
