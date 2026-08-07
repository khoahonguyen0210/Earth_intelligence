# Workflow State Machine — LOCKED

This document freezes the workflow state machine per Task 8.2 of the
Execution Handbook. It is not a brainstorming document. It builds on
`docs/workflow-dag-schema.md` (Task 8.1) rather than redefining it, and
Task 8.3 (DAG execution) drives real nodes through this machine rather
than inventing its own transition rules.

## The transition table (fixed)

```text
PENDING   -> READY, CANCELLED
READY     -> RUNNING, CANCELLED
RUNNING   -> SUCCEEDED, FAILED, RETRYING, CANCELLED
RETRYING  -> RUNNING, CANCELLED
SUCCEEDED -> (terminal)
FAILED    -> (terminal)
CANCELLED -> (terminal)
```

```text
backend/src/main/java/com/example/backend/workflow/WorkflowStateMachine.java
backend/src/main/java/com/example/backend/workflow/IllegalStateTransitionException.java
```

## Why PENDING never goes straight to RUNNING

A `WorkflowNode` (Task 8.1) can have dependencies a plain `Forecast`
(Task 6.1-6.6) never has. `READY` is the state that records "this
node's dependencies have all resolved, it may now be dispatched" --
collapsing it into `PENDING` would lose the one fact Task 8.3's
scheduler actually needs to decide what to run next. This is also
exactly why `Forecast.Status` (six states, no `READY`) and
`WorkflowNode.Status` (seven states, `READY` included) differ: a
standalone forecast has no dependencies to wait on, so for it
`PENDING` already means "eligible to run" -- `ForecastWorker.process`
picks up `PENDING` forecasts directly. A `WorkflowNode` cannot make that
same assumption.

## Why RETRYING re-enters at RUNNING, not READY

A retry re-dispatches a node whose dependencies were already satisfied
once; it does not need to re-check them. This mirrors real, already-
shipped precedent: `ForecastWorker.process` (Task 6.5/6.6) already
treats `PENDING` and `RETRYING` as equally eligible to become `RUNNING`
for a `Forecast`. Losing the same shortcut for `WorkflowNode` would
handle a retry inconsistently with a job the project already runs in
production-shaped code.

## Why cancellation is legal from every non-terminal state

The handbook's own reliability language -- Task 6.6's "worker timeout ->
recover/retry", Task 9.5's fault-injection expectations that a
controlled kill still reaches "a correct terminal state" -- assumes
in-flight and queued work can both be stopped, not only work that
hasn't started yet. Restricting `CANCELLED` to just `PENDING`/`READY`
would leave no legal way to record "this was cancelled while running,"
which is a real, expected outcome, not an error case to special-case
around.

## What this task validates

`WorkflowStateMachine.transition(node, to, updatedAt)` is the one path
meant to change a node's status: it raises
`IllegalStateTransitionException` on an illegal request rather than
silently applying it -- the same "cannot bypass the validator" property
Task 7.2's plan validator already guarantees for a `Plan`.
`tests/workflow/WorkflowStateMachineTest.java` checks the full 7x7
state-pair cross-product against the exact table above (not spot
checks), plus that every terminal state truly has zero legal outgoing
transitions and that `transition` both applies a legal change and
rejects an illegal one with a message naming the task, the current
state, and the attempted state.

## What this document does not define

Nothing here decides *when* a real node should transition -- computing
"all of this node's dependencies have SUCCEEDED, so it may become
READY" or "this failure was transient, retry it" is Task 8.3 (DAG
execution)'s job, using the real dependency graph `Workflow.validate()`
(Task 8.1) already proves is well-formed and the real transient/
permanent distinction `ForecastOutcome` (Task 6.6) already established
for a single job. This task only fixes which transitions are legal once
something else decides to attempt one.
