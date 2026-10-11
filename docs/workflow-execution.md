# Workflow DAG Execution — LOCKED

This document freezes DAG execution. It is not a brainstorming
document. It builds on `docs/workflow-dag-schema.md` and
`docs/workflow-state-machine.md` rather than redefining
either.

## The two types

```text
backend/src/main/java/com/example/backend/workflow/WorkflowTaskDispatcher.java
backend/src/main/java/com/example/backend/workflow/WorkflowExecutor.java
```

`WorkflowTaskDispatcher` is a one-method seam (`dispatch(WorkflowNode) ->
DispatchOutcome`) between the DAG-walking algorithm and whatever
actually performs a node's real work. `DispatchOutcome` deliberately
mirrors `ForecastOutcome` exactly: success/output, or a
failure marked transient (worth retrying) vs permanent (retrying would
only reproduce it) -- the same distinction, not a second, competing one.

`WorkflowExecutor.execute(Workflow)` walks every node to a terminal
state and returns the finished `Workflow`. It is synchronous and
single-call: it loops until nothing changes in a full pass over every
node, rather than polling a queue across separate invocations the way
`ForecastWorker` does for one job. This is the right shape to
prove the algorithm itself -- dependency ordering, fan-out, failure
propagation, retry -- against the example DAG; a
restart-safe, queue-backed version (the natural next step once this
plugs into a real dispatcher) is later work, not this task's.

## The algorithm

```text
repeat until no node changes in a full pass:
  for each PENDING node:
    if any dependency is FAILED or CANCELLED -> CANCELLED
      (this node is unreachable, not itself a failure)
    else if every dependency is SUCCEEDED -> READY
      (a node with zero dependencies is trivially "every dependency
      SUCCEEDED" and becomes READY on the first pass)
    else -> unchanged, still waiting

  for each READY or RETRYING node:
    -> RUNNING, dispatch(node), attempt += 1
    if the outcome succeeded -> SUCCEEDED, outputRef set
    else if transient and attempt < max_attempts -> RETRYING
    else -> FAILED, error set
      (a permanent failure always lands here on its first attempt --
      exactly ForecastWorker's own rule)
```

Every status change goes through `WorkflowStateMachine`, so
an algorithm bug that tried an illegal transition would raise
`IllegalStateTransitionException` rather than silently corrupting a
node's state -- `WorkflowExecutorTest` caught exactly this once, live:
the first draft transitioned a `RETRYING` node to `RUNNING` twice (once
in the dispatch loop, once again inside the run-a-node helper), and the
state machine's own legality check is what surfaced it as a real test
failure (`RUNNING -> RUNNING` is not a legal edge) rather than a subtle
runtime bug.

## Why a failed dependency cancels, not fails, its dependents

A node that never actually ran was never itself a failure -- the real
failure already lives on the dependency's own node, with its own
`error`. Marking dependents `CANCELLED` keeps that distinction visible
in the final `Workflow` rather than smearing one real failure across
every node downstream of it.

## Result

`WorkflowExecutorTest` proves, against fake dispatchers (no network, no
Python, no cost):

```text
[x] the linear-chain example (get_data -> validate ->
    build_features -> run_forecast) runs to completion in dependency
    order
[x] the fan-out example (run_forecast -> {get_result_evidence,
    generate_map}) runs both children after their shared dependency
[x] a permanent failure cancels every downstream dependent, and the
    cancelled nodes are never actually dispatched
[x] an independent branch is unaffected by a sibling's failure
[x] a transient failure is retried in-line and can succeed on a later
    attempt, with attempt counted correctly
[x] a transient failure that exhausts max_attempts ends FAILED, without
    exceeding max_attempts real dispatch calls
[x] execute() rejects a structurally invalid (cyclic) workflow before
    dispatching anything
[x] an empty workflow executes trivially
```

## What this document does not define

There is no real `WorkflowTaskDispatcher` implementation here -- bridging
each of the planner's tools to its actual caller
(`docs/planner-tool-schemas.md`'s own mapping: resolve_region/get_data/
calculate_statistics/generate_map/get_result_evidence to the real Python
functions, run_forecast to the existing `POST /forecasts` pipeline), and
resolving a step's `$step_id.field` references against an
already-completed dependency's `outputRef`, is real integration work a
later task must still do. There is also no code here that turns a
Python `Plan` into a `Workflow` -- that conversion is the
other half of wiring the planner to real execution. Persisting a
`Workflow`'s state as it runs (surviving a controller/worker restart,
per the later persistence work) is not implemented either: `execute`
holds everything in memory for the duration of one call.
