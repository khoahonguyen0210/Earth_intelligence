# Multi-Worker Scaling — LOCKED

This document freezes the multi-worker scaling benchmark. It is not a
brainstorming document. It runs
`docs/one-worker-baseline.md`'s exact implementation at
1/2/4/8 workers against the exact same frozen workload
rather than building a second implementation to compare against.

## The implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/scaling.py
scripts/distributed/run_scaling_benchmark.py
```

`run_scaling_benchmark(workload, context, worker_counts=(1, 2, 4, 8))`
calls `run_distributed_inference` (unmodified) once per worker
count, against one shared `RunContext` -- the same loaded data and the
same fitted model object for every point, not a fresh load/fit per
worker count. This is what makes "keep workload/data/model fixed" (the
handbook's own words for this task) literally true rather than only
nominally true. Metrics are the handbook's own formulas, computed
against the first (`num_workers=1`) point's wall time as T1:

```text
speedup(n)    = T1 / Tn
efficiency(n) = speedup(n) / n
```

## Result

A real run of `scripts/distributed/run_scaling_benchmark.py` (500 real
tiles, the real fitted model from the one-worker baseline, `docker`/Redis/Postgres not
involved -- this is pure Python multiprocessing):

```text
workers   wall_s   speedup   efficiency
      1    0.581     1.000        1.000
      2    9.700     0.060        0.030
      4   18.317     0.032        0.008
      8   69.555     0.008        0.001
```

**More workers made this workload slower, not faster -- monotonically,
at every step.** This is the real, measured answer, not a bug in the
implementation: `WorkerChunkResult`'s `cpu_seconds` per worker for this
workload's actual computation is a small fraction of a second (matching
the one-worker baseline: 500 tiles cost 0.734 total CPU-seconds), but this
project's development machine is Windows, where `multiprocessing` uses
the `spawn` start method -- every additional worker process pays the
cost of starting a brand-new Python interpreter and re-importing the
entire `ml` package (numpy, xgboost, scikit-learn, rasterio, ...) from
scratch, which this same investigation (the one-worker baseline's own smoke-testing)
already observed taking multiple real seconds per process, before that
worker does a single tile's worth of real work. At this workload size,
that fixed per-process startup cost totally dominates the genuinely
tiny amount of real parallelizable compute, so adding workers only adds
more of that fixed cost without a compensating benefit.

## Why this is the correct benchmark to report, not a reason to redesign it

The handbook's goal here is explicitly "a measured answer to whether
spatial parallelism actually improves workload time/throughput" -- not
a guarantee that it does. An earlier step deliberately fixed a workload
(500 tiles against small real sample data) sized for a fast local
baseline (the one-worker baseline), not for showing off parallelism at its best; this
result is what that same fixed, honest choice produces when actually
measured with more workers, and reporting it as found is truer to the
handbook's own intent than re-picking a bigger workload after the fact
to manufacture a better-looking number. Later bottleneck-identification
work is where naming process-spawn/coordination overhead as
the actual limiting factor -- rather than CPU, I/O, network, database,
or serialization -- belongs; this document's job was only to measure and
report the scaling numbers themselves.

## Result artifact

```text
data/processed/distributed/scaling_benchmark.json
```

Gitignored, regenerable, like every other `data/processed/` artifact in
this project. Contains the full workload record, the data-loading
stage timing, whether the synthetic model-fitting fallback was used
(the one-worker baseline's own documented, expected case), and each of the four
worker-count points (`DistributedRunResult` plus its `speedup`/
`efficiency`).

## What this document does not define

Diagnosing *why* in more depth than "process-spawn overhead, observed
directly" -- with real profiling tooling, breaking down exactly how much
of each worker's wall time is interpreter startup versus import versus
real compute -- is later bottleneck-identification work's job. Whether a different worker model
(a persistent pool reused across many workloads, threads instead of
processes, a Linux/fork-based deployment target) would change this
result is a real, open question this task does not answer -- it measures
what this project's actual current implementation and platform produce,
not every implementation that could exist.
