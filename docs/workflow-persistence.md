# Workflow Persistence

This step gives the `workflows` and `jobs` tables
(`docs/persistence-schema.md`) their first read and write path, and
stores the `Workflow` and `WorkflowNode` shapes from the workflow DAG
schema. It does not change either definition.

## Schema change

```text
backend/src/main/resources/db/migration/V3__workflow_persistence.sql
```

`jobs` had `id, job_type, status, created_at, updated_at, error`. It
gains `task_id`, `workflow_id` (a foreign key to `workflows`),
`dependencies` (jsonb), `attempt`, `input_ref` and `output_ref`.

`task_id` is a new column instead of a reuse of `id`, because a
`WorkflowNode`'s `taskId` (for example `"get_data"`) is unique only
within one workflow: every run of the same workflow uses the same task
IDs. So `id` is built as `workflow_id + ":" + task_id`, and a partial
unique index on `(workflow_id, task_id)` enforces the rule.

`input_ref` and `output_ref` are `TEXT`, not `jsonb`. The workflow DAG
schema describes them as opaque reference strings (a JSON blob, an
object-storage key or a `$step_id.field` reference), which are not
always valid JSON.

## Types

```text
backend/src/main/java/com/example/backend/workflow/WorkflowEntity.java
backend/src/main/java/com/example/backend/workflow/JobEntity.java
backend/src/main/java/com/example/backend/workflow/WorkflowJpaRepository.java
backend/src/main/java/com/example/backend/workflow/JobJpaRepository.java
backend/src/main/java/com/example/backend/workflow/WorkflowStore.java
```

`WorkflowStore.save` and `find` convert between `Workflow`/`WorkflowNode`
and the entities, in the same way that `ForecastStore` converts
`Forecast` and `ForecastEntity`. Nothing else in the workflow package
needs to know that these are Postgres rows.

## Recovery after a restart

The requirement: restart a worker or controller during a controlled run
and check that the active state can be recovered. `WorkflowStoreTest`
is a `@SpringBootTest` against local Postgres (run `docker compose up -d`
in `infra/docker/` first, as for `BackendApplicationTests`). It does the
following:

```text
1. Save a workflow in the middle of a run: one node SUCCEEDED, one
   RUNNING (as if the process died while it ran), two still PENDING.
2. Load it with a new WorkflowStore.find call, with no shared memory
   with the code that saved it.
3. Give the loaded Workflow to a new WorkflowExecutor, which stands in
   for a process started after the restart.
4. Check that every node reaches SUCCEEDED.
```

Writing this test showed that `WorkflowExecutor` needed a fix for step 4.
A node loaded in `RUNNING` status had no allowed way to enter `RUNNING`
again: the state machine has no `RUNNING -> RUNNING` transition, and
after a restart nothing is running anymore. At the start of `execute`,
`WorkflowExecutor.advance` now treats a node that is already `RUNNING`
as left over from an interrupted attempt. It moves the node through the
allowed `RUNNING -> RETRYING -> RUNNING` path before dispatching it
again, and counts this as a retry attempt.

## Out of scope

The code that runs a workflow calls `save` itself. There is no
automatic checkpoint after every node transition. No request path uses
`WorkflowStore` and `WorkflowExecutor` together yet, such as a
controller endpoint or a Redis-queued worker like `ForecastWorker`.
Connecting a `WorkflowTaskDispatcher` to an HTTP or queue entry point is
still the open gap described in `docs/workflow-execution.md`.
