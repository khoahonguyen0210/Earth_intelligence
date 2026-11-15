# Workflow DAG Schema

This document defines the shape of a workflow DAG. The state machine and
the DAG executor use this shape and do not redefine it.

## Types

```text
backend/src/main/java/com/example/backend/workflow/WorkflowNode.java
backend/src/main/java/com/example/backend/workflow/Workflow.java
```

`WorkflowNode` has the fields required for a DAG node:

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

`Workflow` holds the DAG: `id`, `name`, `description`, `createdAt` and
its `nodes`.

## Why Java, not Python

In this architecture, Java controls requests, jobs and workflows, and
Python does the Earth-data and ML computation. The async job, worker
and retry code (`ForecastQueue`, `ForecastWorker`, `RedisForecastQueue`)
is already on the Java side. A DAG of nodes extends that single-job
model to several dependent steps, so it belongs next to it, not in
`ml/`.

The Python planner's `Plan` and `PlanStep` (`planner.validator`) belong
to an earlier stage of the same pipeline. A `Plan` is a fixed proposal
from the LLM that has not run. A `Workflow` of `WorkflowNode`s is what a
validated `Plan` becomes once it is accepted for execution. The fields
of `WorkflowNode` match those of `PlanStep` on purpose
(`taskId`/`taskType`/`dependencies` and `step_id`/`tool`/`depends_on`),
plus the runtime state that a `Plan` does not have (`status`,
`attempt`, `inputRef`, `outputRef`, timestamps and `error`). Turning a
`Plan` into a `Workflow` is part of the execution work.

## Schema only at this stage

The `jobs` and `workflows` tables already exist in Postgres
(`docs/persistence-schema.md`), but at this stage no Java entity or
repository reads or writes them. Adding JPA entities and repositories
before the executor gives them a caller would add an abstraction with
no use and no test, which `docs/persistence-schema.md` already chose not
to do for the same two tables. They are connected later, in
`docs/workflow-persistence.md`.

## Validation

A `Workflow` must be a directed acyclic graph, and nothing else checks
that a list of nodes is one. So `Workflow.validate()` checks the
structure:

```text
[ ] every task_id is unique
[ ] no node depends on itself
[ ] every dependency names an existing task_id in the same workflow
[ ] the dependency graph has no cycle (Kahn's algorithm: a DAG always
    has a full topological order; a graph with a cycle never does)
```

This is the same kind of check that the plan validator runs on a
`Plan`'s `depends_on` references, applied to the Java type instead of
copying logic across languages. It checks structure only. Whether a
node's `taskType` names an existing tool, whether its `inputRef`
resolves, and which status changes are allowed belong to the state
machine and the executor.

`tests/workflow/WorkflowTest.java` checks that the linear and fan-out
shapes from the project's example pass
(`get_data -> validate -> build_features -> run_forecast`, then
`get_result_evidence` and `generate_map`). It also checks that a
duplicate id, a self-dependency, an unknown dependency, a two-node
cycle and a longer cycle are each caught.

## Out of scope

This schema does not run a workflow, change a node's status or store
anything. Execution is in `docs/workflow-execution.md` and storage in
`docs/workflow-persistence.md`. No code turns a Python `Plan` into a
`Workflow` yet.
