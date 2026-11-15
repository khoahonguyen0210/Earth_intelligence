# Workflow DAG Execution

This document describes how a workflow DAG is executed. It builds on
`docs/workflow-dag-schema.md` and `docs/workflow-state-machine.md` and
does not change either.

## Types

```text
backend/src/main/java/com/example/backend/workflow/WorkflowTaskDispatcher.java
backend/src/main/java/com/example/backend/workflow/WorkflowExecutor.java
```

`WorkflowTaskDispatcher` has one method, `dispatch(WorkflowNode) ->
DispatchOutcome`. It separates the code that walks the DAG from the code
that does each node's work. `DispatchOutcome` follows `ForecastOutcome`:
success with an output, or a failure marked as temporary (worth
retrying) or permanent (a retry would only repeat it). This is the same
distinction, not a second one.

`WorkflowExecutor.execute(Workflow)` moves every node to a final state
and returns the finished `Workflow`. It is synchronous and runs in one
call: it loops until a full pass over all nodes changes nothing, instead
of polling a queue across separate calls as `ForecastWorker` does for a
single job. This shape is enough to prove the algorithm (dependency
order, fan-out, failure propagation and retry) on the example DAG. A
version that survives restarts and uses a queue is the next step once a
working dispatcher exists.

## Algorithm

```text
repeat until no node changes in a full pass:
  for each PENDING node:
    if any dependency is FAILED or CANCELLED -> CANCELLED
      (this node cannot be reached; it did not fail itself)
    else if every dependency is SUCCEEDED -> READY
      (a node with no dependencies meets this at once and becomes
      READY on the first pass)
    else -> unchanged, still waiting

  for each READY or RETRYING node:
    -> RUNNING, dispatch(node), attempt += 1
    if the outcome succeeded -> SUCCEEDED, outputRef set
    else if temporary and attempt < max_attempts -> RETRYING
    else -> FAILED, error set
      (a permanent failure always ends here on its first attempt,
      the same rule as in ForecastWorker)
```

Every status change goes through `WorkflowStateMachine`, so a bug that
tries a forbidden transition raises `IllegalStateTransitionException`
instead of quietly corrupting a node's state. `WorkflowExecutorTest`
caught one such bug: the first draft moved a `RETRYING` node to
`RUNNING` twice, once in the dispatch loop and again inside the helper
that runs a node. The state machine rejected `RUNNING -> RUNNING`, so the
bug showed up as a test failure instead of a subtle runtime error.

## Why a failed dependency cancels its dependents

A node that never ran did not fail. The failure belongs to the
dependency's node, which holds its own `error`. Marking the dependents
`CANCELLED` keeps this clear in the final `Workflow`, instead of
spreading one failure over every node after it.

## Result

`WorkflowExecutorTest` checks the following with fake dispatchers (no
network, no Python, no cost):

```text
[x] the linear example (get_data -> validate -> build_features ->
    run_forecast) runs to the end in dependency order
[x] the fan-out example (run_forecast -> {get_result_evidence,
    generate_map}) runs both children after their shared dependency
[x] a permanent failure cancels every dependent below it, and the
    cancelled nodes are never dispatched
[x] an independent branch is not affected by a sibling's failure
[x] a temporary failure is retried in place and can succeed on a later
    attempt, with the attempts counted correctly
[x] a temporary failure that uses up max_attempts ends FAILED, with no
    more than max_attempts dispatch calls
[x] execute() rejects an invalid (cyclic) workflow before dispatching
    anything
[x] an empty workflow finishes at once
```

## Out of scope

There is no working `WorkflowTaskDispatcher` yet. Connecting each
planner tool to its actual caller is still to do: resolve_region,
get_data, calculate_statistics, generate_map and get_result_evidence
map to Python functions, and run_forecast maps to the existing
`POST /forecasts` pipeline (see the mapping in
`docs/planner-tool-schemas.md`). So is replacing a step's
`$step_id.field` references with the `outputRef` of a finished
dependency. No code turns a Python `Plan` into a `Workflow` either.
`execute` keeps everything in memory for one call; saving state between
restarts is covered in `docs/workflow-persistence.md`. The Ask Earth
pipeline runs plans with its own simpler executor, `execute_plan`
(`docs/ask-earth.md`).
