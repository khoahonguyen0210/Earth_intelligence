# Fault-Injection Test — LOCKED

This document freezes the fault-injection test. It is not a
brainstorming document. It runs a real killed worker against
`docs/multi-worker-scaling.md`'s distributed execution, and
its own real recovery time connects directly to
`docs/bottleneck-identification.md`'s finding.

## The implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/fault_tolerance.py
scripts/distributed/run_fault_injection_test.py
```

The existing `run_distributed_inference` dispatches every chunk with
one blocking `Pool.map` call -- fine for a happy-path benchmark, but a
single call cannot detect or retry one crashed chunk without losing or
re-running every other chunk's already-completed real result.
`run_with_fault_tolerance` dispatches each chunk individually via
`Pool.apply_async`, polls every pending result for readiness, and
retries -- redispatching to the very same pool, without re-injecting the
crash -- whichever chunk does not complete within `task_timeout_seconds`.

`ChunkTask.inject_crash` (an extension of the existing `ChunkTask`) makes one
worker call `os._exit(1)` immediately instead of doing any real work --
observably identical, from the parent's point of view, to that worker
being killed externally, and deterministic/reproducible in a way an
actual external `kill -9` timed to land on the right process could not
be. Confirmed directly against the real interpreter before writing the
dispatcher: a worker that calls `os._exit` leaves its `AsyncResult`
simply never completing -- `.get()` raises `multiprocessing.TimeoutError`
after the caller's own timeout, never a distinct "worker died"
exception -- which is why detection here is timeout-based, not
exception-type-based, and why the pool's other worker(s) are confirmed
to keep running and returning real results throughout.

## Result

A real run of `scripts/distributed/run_fault_injection_test.py` (500
real tiles, 4 real workers, chunk 0's worker genuinely killed):

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

The four checks, each verified against this real run:

```text
[x] failure detected      -- chunk 0's failure_detected=true
[x] task retried           -- chunk 0's attempts=2 (one real retry)
[x] no final result lost   -- 500/500 tiles recovered; every chunk's
                               result is present, including the three
                               that never failed at all
[x] terminal state correct -- every chunk ends SUCCEEDED, none left
                               stuck or silently dropped
```

Recovery time is real and reported per chunk (`total_recovery_seconds`
sums every chunk that needed one) -- this run's 1.154s reflects a
replacement worker that happened to be ready quickly; a slower
environment or a busier pool can and did (in earlier local runs while
building this test) take substantially longer, for a real, understood
reason below.

## Recovery time connects directly to the bottleneck-identification finding

While building this test's timeout value, a real, informative failure
showed up: with a short `task_timeout_seconds` (5s), a retried chunk
would sometimes still not complete in time and trigger a second,
unnecessary retry, even though nothing was actually still broken. The
cause: `multiprocessing.Pool` replaces a dead worker with a brand-new
process, and that replacement pays the exact same real cold-start cost
already measured directly elsewhere (multiple real seconds -- spawning a
fresh interpreter and re-importing the whole `ml` package: numpy,
xgboost, scikit-learn, rasterio) before it can run anything at all. A
timeout tight enough to detect a real crash promptly can be too tight
to tell "still cold-starting a legitimate replacement" apart from
"genuinely still dead" -- `task_timeout_seconds=30` in both the test
suite and the real script above gives real replacement cold-starts
comfortable room, at the cost of detecting a genuine permanent failure
more slowly. This is the same coordination overhead already named as
this pipeline's actual bottleneck, now shown to also be the dominant
cost of *recovering* from a failure, not just of scaling up in the
first place.

## Result artifact

```text
data/processed/distributed/fault_injection_report.json
```

Gitignored, regenerable, like every other `data/processed/` artifact in
this project.

## What this document does not define

This dispatcher is a fault-tolerant alternative to the existing plain
`Pool.map`, not a replacement wired into those earlier benchmarks --
their numbers stand as measured, on the simpler, non-fault-tolerant
implementation originally specified. Choosing a
timeout value in production (rather than for a controlled, one-shot
test) that correctly balances "detect a real failure promptly" against
"do not mistake a legitimate cold start for a failure" is a real,
unresolved tuning question this task surfaces but does not solve
generally.
