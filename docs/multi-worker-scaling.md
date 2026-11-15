# Multi-Worker Scaling

This benchmark runs the implementation from
`docs/one-worker-baseline.md` with 1, 2, 4 and 8 workers on the same
frozen workload. It does not build a second implementation to compare
against.

## Implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/scaling.py
scripts/distributed/run_scaling_benchmark.py
```

`run_scaling_benchmark(workload, context, worker_counts=(1, 2, 4, 8))`
calls `run_distributed_inference` (unchanged) once per worker count
with one shared `RunContext`. Every run uses the same loaded data and
the same fitted model object; nothing is loaded or fitted again per
worker count. This keeps the workload, data and model fixed in fact,
not only in name. The metrics use the standard formulas, with the wall
time of the first run (`num_workers=1`) as T1:

```text
speedup(n)    = T1 / Tn
efficiency(n) = speedup(n) / n
```

## Result

A run of `scripts/distributed/run_scaling_benchmark.py` (500 tiles,
the fitted model from the one-worker baseline, and no Docker, Redis or
Postgres; this is plain Python multiprocessing):

```text
workers   wall_s   speedup   efficiency
      1    0.581     1.000        1.000
      2    9.700     0.060        0.030
      4   18.317     0.032        0.008
      8   69.555     0.008        0.001
```

**Each added worker made this workload slower.** This is the measured
answer, not a bug. The compute per worker (`cpu_seconds` in
`WorkerChunkResult`) is a small fraction of a second; in the one-worker
baseline, all 500 tiles took 0.734 CPU-seconds in total. The
development machine runs Windows, where `multiprocessing` uses the
`spawn` start method. Every extra worker process starts a new Python
interpreter and imports the whole `ml` package again (numpy, xgboost,
scikit-learn, rasterio and others). Tests for the one-worker baseline
had already seen this take several seconds per process, before the
worker computes a single tile. At this workload size, that fixed
start-up cost is far larger than the small amount of compute that can
run in parallel, so each added worker only adds more of the fixed cost.

## Why this result is reported as it is

The goal was to measure whether spatial parallelism improves time and
throughput, not to show that it does. The workload (500 tiles on small
sample data) was fixed earlier for a fast local baseline, not chosen to
show parallelism at its best. This result is what that fixed choice
gives with more workers. Choosing a bigger workload after seeing the
numbers, just to get a better result, would defeat the purpose.
`docs/bottleneck-identification.md` later confirms that process
start-up (coordination) is the limiting factor, rather than CPU, I/O,
network, database or serialization.

## Result file

```text
data/processed/distributed/scaling_benchmark.json
```

Like every file under `data/processed/`, it is ignored by git and can
be rebuilt. It holds the full workload record, the data-loading time,
whether the synthetic model-fitting fallback was used (an expected
case, documented in the one-worker baseline), and each of the four
worker-count results (`DistributedRunResult` with its `speedup` and
`efficiency`).

## Out of scope

A deeper breakdown, such as how much of each worker's wall time is
interpreter start-up, imports or compute, is in
`docs/bottleneck-identification.md`. Whether another worker model
(a persistent pool reused across workloads, threads instead of
processes, or a Linux target with `fork`) would change the result is an
open question. This benchmark measures the current implementation on
the current platform only.
