# Workflow State Machine

This document defines the states of a workflow node and the allowed
changes between them. It builds on `docs/workflow-dag-schema.md`, and
the DAG executor uses this machine instead of its own rules.

## Transition table

```text
PENDING   -> READY, CANCELLED
READY     -> RUNNING, CANCELLED
RUNNING   -> SUCCEEDED, FAILED, RETRYING, CANCELLED
RETRYING  -> RUNNING, CANCELLED
SUCCEEDED -> (final)
FAILED    -> (final)
CANCELLED -> (final)
```

```text
backend/src/main/java/com/example/backend/workflow/WorkflowStateMachine.java
backend/src/main/java/com/example/backend/workflow/IllegalStateTransitionException.java
```

## Why PENDING never goes straight to RUNNING

A `WorkflowNode` can have dependencies, which a plain `Forecast` never
has. `READY` records that all of a node's dependencies have finished and
the node may now be dispatched. Merging it into `PENDING` would lose the
one fact the executor needs to decide what to run next.

This is also why `Forecast.Status` (six states, no `READY`) differs
from `WorkflowNode.Status` (seven states, with `READY`). A single
forecast has nothing to wait for, so for it `PENDING` already means
"may run", and `ForecastWorker.process` takes `PENDING` forecasts
directly. A `WorkflowNode` cannot assume this.

## Why RETRYING goes back to RUNNING, not READY

A retry dispatches a node whose dependencies were already met once, so
there is no need to check them again. The forecast flow already works
this way: `ForecastWorker.process` treats `PENDING` and `RETRYING` as
equally able to become `RUNNING`. Doing otherwise for `WorkflowNode`
would handle a retry differently from the job flow the project already
runs.

## Why every non-final state can be cancelled

The reliability work expects that both queued and running work can be
stopped: a worker timeout leads to recovery or a retry, and a
controlled kill in the fault-injection tests must still reach a correct
final state. If only `PENDING` and `READY` could become `CANCELLED`,
there would be no allowed way to record "cancelled while running",
which is a normal, expected outcome and not an error.

## Validation

`WorkflowStateMachine.transition(node, to, updatedAt)` is the one way to
change a node's status. It raises `IllegalStateTransitionException` for
a forbidden change instead of applying it, in the same way that the
plan validator cannot be skipped for a `Plan`.

`tests/workflow/WorkflowStateMachineTest.java` checks all 7x7 pairs of
states against the table above, not just a few samples. It also checks
that no final state has an allowed outgoing change, and that
`transition` applies an allowed change and rejects a forbidden one with
a message naming the task, the current state and the requested state.

## Out of scope

The state machine does not decide when a node should change state.
Working out that "all of this node's dependencies have SUCCEEDED, so it
may become READY", or that "this failure was temporary, so retry it", is
the executor's job. It uses the dependency graph that
`Workflow.validate()` checks, and the split between temporary and
permanent failures that `ForecastOutcome` defines for a single job. The
state machine only fixes which changes are allowed once something else
asks for one.
