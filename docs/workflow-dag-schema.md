# Workflow DAG Schema — LOCKED

This document freezes the workflow DAG schema per Task 8.1 of the
Execution Handbook, the first task of Phase 8. It is not a
brainstorming document. Task 8.2 (state machine) and Task 8.3 (DAG
execution) build against this shape rather than redefining it.

## The two types, and nothing else

```text
backend/src/main/java/com/example/backend/workflow/WorkflowNode.java
backend/src/main/java/com/example/backend/workflow/Workflow.java
```

`WorkflowNode` is exactly the handbook's own field list for a DAG node:

```text
task_id            -> taskId
task_type          -> taskType
dependencies       -> dependencies (List<String> of other nodes' task_id)
status             -> status (WorkflowNode.Status)
attempt            -> attempt
input references   -> inputRef
output references  -> outputRef
timestamps         -> createdAt, updatedAt
error              -> error
```

`Workflow` is the DAG container: `id`, `name`, `description`,
`createdAt`, and its `nodes`.

## Why Java, not Python

The architecture (`docs/PROMPT_SYSTEM.md`) is "Java owns request/job/
workflow control, Python owns Earth-data/ML computation." Phase 6
already put the async job/worker/retry machinery
(`ForecastQueue`/`ForecastWorker`/`RedisForecastQueue`) on the Java
side; a DAG of nodes is the generalization of that same single-job
model to multiple, dependent steps, so it belongs next to it, not in
`ml/`. The Python planner's `Plan`/`PlanStep`
(`planner.validator`, Task 7.2) is a different, earlier stage of the
same pipeline: a `Plan` is a static, unexecuted, LLM-produced proposal;
a `Workflow` of `WorkflowNode`s is what a validated `Plan` becomes once
accepted for real execution. `WorkflowNode`'s fields deliberately line
up with `PlanStep`'s (`taskId`/`taskType`/`dependencies` <->
`step_id`/`tool`/`depends_on`) plus the runtime state a `Plan` does not
carry (`status`/`attempt`/`inputRef`/`outputRef`/timestamps/`error`) --
turning a `Plan` into a `Workflow` is Task 8.3's job, not this one's.

## Schema only, not yet persisted

`jobs` and `workflows` already exist as real, migrated Postgres tables
(Task 6.3, `docs/persistence-schema.md`) but remain schema-only: no
Java entity/repository reads or writes them yet. This task does not
change that. Adding JPA entities/repositories around these types now,
before Task 8.3's execution engine gives them a real caller, would be
exactly the kind of speculative, untested abstraction
`docs/persistence-schema.md` already declined to build for the same two
tables -- wiring `WorkflowNode`/`Workflow` to real rows is explicitly
Task 8.4's job ("Persist workflow state"), not this one's.

## What this task does validate

A `Workflow` is supposed to be a *directed acyclic* graph; nothing else
in the handbook's task list checks that a given node list actually is
one, so `Workflow.validate()` does, structurally:

```text
[ ] every task_id is unique
[ ] no node depends on itself
[ ] every dependency names a real task_id in the same workflow
[ ] the dependency graph has no cycle (Kahn's algorithm: a real DAG
    always admits a full topological order; a graph with a cycle
    never does)
```

This is deliberately the same kind of check Task 7.2's plan validator
already runs for a `Plan`'s `depends_on` references, applied to the
Java-side type instead of duplicating logic across languages. It is
also deliberately *only* structural: whether a node's `taskType` names
a real tool, whether its `inputRef` actually resolves to something, and
which status transitions are legal are Task 8.2 (state machine) and
Task 8.3 (execution)'s concerns -- `tests/workflow/WorkflowTest.java`
proves the linear-chain and fan-out shapes from the handbook's own Task
8.3 example (`get_data -> validate -> build_features -> run_forecast`,
then fanning out to `get_result_evidence`/`generate_map`) pass, and that
a duplicate id, a self-dependency, an unknown dependency, and both a
two-node and a longer cycle are each caught.

## What this document does not define

Nothing here executes a workflow, transitions a node's status, or
persists anything -- those are Tasks 8.2/8.3/8.4. There is no code here
that turns a Python `Plan` into a `Workflow` yet; that conversion, and
whichever process (the existing `ForecastWorker`-style Redis consumer,
or something new) actually walks a `Workflow`'s nodes in dependency
order, is Task 8.3's job.
