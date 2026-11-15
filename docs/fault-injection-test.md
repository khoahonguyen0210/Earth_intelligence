# Fault-Injection Test

This test kills a worker during the distributed run from
`docs/multi-worker-scaling.md` and checks that the run recovers. The
recovery time links back to the finding in
`docs/bottleneck-identification.md`.

## Implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/fault_tolerance.py
scripts/distributed/run_fault_injection_test.py
```

`run_distributed_inference` sends every chunk with one blocking
`Pool.map` call. That works when nothing fails, but one call cannot
detect and retry a single crashed chunk without losing or rerunning the
chunks that already finished. `run_with_fault_tolerance` sends each
chunk on its own with `Pool.apply_async` and polls every pending
result. If a chunk does not finish within `task_timeout_seconds`, it
sends that chunk again to the same pool, this time without the crash.

`ChunkTask.inject_crash` makes one worker call `os._exit(1)` at once,
before doing any work. To the parent process this looks the same as a
worker killed from outside, but unlike a `kill -9` timed by hand, it is
repeatable. A test against the interpreter showed that when a worker
calls `os._exit`, its `AsyncResult` never completes: `.get()` raises
`multiprocessing.TimeoutError` after the caller's timeout, and there is
no separate "worker died" exception. So failure detection is based on
the timeout. The other workers keep running and returning results.

## Result

A run of `scripts/distributed/run_fault_injection_test.py` (500 tiles,
4 workers, the worker for chunk 0 killed):

```text
any_failure_detected:            true
all_chunks_eventually_succeeded: true
total_tiles_recovered:           500 / 500
total_recovery_seconds:          1.154

chunk 0 (killed):  attempts=2  failure_detected=true   result=OK
chunk 1:           attempts=1  failure_detected=false  result=OK
chunk 2:           attempts=1  failure_detected=false  result=OK
chunk 3:           attempts=1  failure_detected=false  result=OK
```

The four checks:

```text
[x] failure detected      chunk 0 has failure_detected=true
[x] task retried          chunk 0 has attempts=2 (one retry)
[x] no final result lost  500/500 tiles recovered; every chunk's
                          result is present, including the three
                          that never failed
[x] final state correct   every chunk ends SUCCEEDED; none is stuck
                          or dropped
```

Recovery time is reported per chunk, and `total_recovery_seconds` adds
up every chunk that needed recovery. In this run, a replacement worker
was ready quickly, so recovery took 1.154 s. Earlier runs during
development took much longer, for the reason below.

## Recovery time and the bottleneck

With a short `task_timeout_seconds` (5 s), a retried chunk sometimes
still did not finish in time, which caused a second retry even though
nothing was broken. `multiprocessing.Pool` replaces a dead worker with a
new process, and that process pays the same start-up cost measured in
`docs/bottleneck-identification.md`: several seconds to start a new
interpreter and import the whole `ml` package (numpy, xgboost,
scikit-learn, rasterio). A timeout short enough to catch a crash quickly
can be too short to tell a slow new worker from a dead one. The test
suite and the script both use `task_timeout_seconds=30`, which leaves
enough time for a new worker to start, at the cost of detecting a
permanent failure more slowly. The start-up cost that limits scaling is
also the main cost of recovering from a failure.

## Result file

```text
data/processed/distributed/fault_injection_report.json
```

Like every file under `data/processed/`, it is ignored by git and can
be rebuilt.

## Limits

This dispatcher is a fault-tolerant alternative to `Pool.map`. The
earlier benchmarks do not use it, and their numbers stand as measured
on the simpler dispatcher. Choosing a production timeout that catches
failures quickly without mistaking a slow start for a failure is still
an open question.
