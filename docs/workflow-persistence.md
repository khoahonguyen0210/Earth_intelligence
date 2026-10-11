# Workflow Persistence — LOCKED

This document freezes workflow persistence. It is not a
brainstorming document. It gives `workflows`/`jobs`
(`docs/persistence-schema.md`) their first real read/write
path, and gives the workflow DAG schema's `Workflow`/`WorkflowNode`
shape durable storage, rather than redefining either.

## Schema change

```text
backend/src/main/resources/db/migration/V3__workflow_persistence.sql
```

`jobs` (previously `id, job_type, status, created_at,
updated_at, error`) gains `task_id`, `workflow_id` (FK to `workflows`),
`dependencies` (jsonb), `attempt`, `input_ref`, `output_ref`. A new
`task_id` column, not a reuse of `id`, because a `WorkflowNode`'s
`taskId` (e.g. `"get_data"`) is only unique *within* one workflow --
the same shape's every run reuses the same task ids -- so `id` is
synthesized instead as `workflow_id + ":" + task_id`, with a partial
unique index on `(workflow_id, task_id)` enforcing the real constraint.
`input_ref`/`output_ref` are `TEXT`, not `jsonb`: the workflow DAG
schema's own docstring already calls these opaque reference strings
(a JSON blob, an
object-storage key, a `$step_id.field` reference), not guaranteed valid
JSON on their own.

## The two types

```text
backend/src/main/java/com/example/backend/workflow/WorkflowEntity.java
backend/src/main/java/com/example/backend/workflow/JobEntity.java
backend/src/main/java/com/example/backend/workflow/WorkflowJpaRepository.java
backend/src/main/java/com/example/backend/workflow/JobJpaRepository.java
backend/src/main/java/com/example/backend/workflow/WorkflowStore.java
```

`WorkflowStore.save`/`find` do the `Workflow`/`WorkflowNode` <-> entity
conversion, the exact same shape `ForecastStore` already
uses for `Forecast`/`ForecastEntity` -- nothing else in the workflow
package needs to know these are Postgres rows.

## What this task proves

The acceptance test for this task: "Restart a worker/
controller during a controlled run and verify active state can be
recovered." `WorkflowStoreTest` (a real `@SpringBootTest` against local
Postgres -- `docker compose up -d` in `infra/docker/` first, same
requirement `BackendApplicationTests` already has) proves this for
real:

```text
1. Save a workflow mid-run: one node SUCCEEDED, one RUNNING (as if a
   process died while it was in flight), two still PENDING.
2. Load it back through a brand-new WorkflowStore.find call -- no
   shared in-memory state with whatever saved it.
3. Hand the reloaded Workflow to a brand-new WorkflowExecutor --
   standing in for a freshly started process after the restart.
4. Assert every node reaches SUCCEEDED.
```

Making step 4 possible required a real fix to `WorkflowExecutor`
itself, found by writing this exact test: a node loaded back in
`RUNNING` status has no legal way to re-enter `RUNNING` again (the
state machine's table has no `RUNNING -> RUNNING` edge -- there is no such thing
as "still running" across a restart, since nothing is actually running
anymore). `WorkflowExecutor.advance` now treats a node found already
`RUNNING` at the very start of `execute` as what it can only be -- a
leftover from an interrupted attempt -- and moves it through the legal
`RUNNING -> RETRYING -> RUNNING` path before re-dispatching, counting
it as a real retry attempt. This is a genuine, load-bearing behavior
change this task's own test discovered a need for, not a hypothetical.

## What this document does not define

`save` is called explicitly by whatever runs a workflow; there is no
scheduled/automatic checkpointing after every single node transition,
and no caller yet that actually invokes `WorkflowStore`/`WorkflowExecutor`
together in a real request path (a controller endpoint, a Redis-queued
worker the way `ForecastWorker` already is for a single job). Wiring a
real `WorkflowTaskDispatcher` and a real HTTP/queue entry point remains
`docs/workflow-execution.md`'s documented gap, unchanged by this task.
