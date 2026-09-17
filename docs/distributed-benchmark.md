# Final Distributed Benchmark — LOCKED

This document records the final distributed benchmark. It is
not a brainstorming document.

This task asks for a final 1/2/4/8-worker comparison (runtime,
throughput, speedup, efficiency, failure/recovery). Unlike the ML and
ablation benchmarks, the underlying benchmarks here were never blocked on missing
real data -- the scaling benchmark and the fault-injection
test (`docs/multi-worker-scaling.md`, `docs/fault-injection-test.md`)
already measure real computational cost against a real, fixed workload;
they were never waiting on real fire history the way model accuracy
was. This task re-runs both frozen scripts (`scripts/distributed/
run_scaling_benchmark.py`, `run_fault_injection_test.py`, both on the
`benchmark-v1` list) unchanged, to confirm the numbers still hold on
the current code, and reports runtime/throughput/speedup/efficiency
alongside failure/recovery in one place for the first time.

## Runtime, throughput, speedup, efficiency

`data/processed/distributed/scaling_benchmark.json`, 500 real tiles,
one shared fitted model and loaded data across every point:

```text
workers   actual   wall_s    throughput(tiles/s)  cpu_s    peak_mb   speedup   efficiency
      1        1    0.851               587.49     1.14      1.81      1.000       1.000
      2        2    9.488                52.70      2.61      1.66      0.090       0.045
      4        4   12.109                41.29      5.58      1.61      0.070       0.018
      8        8   22.381                22.34     13.72      1.58      0.038       0.005
```

**More workers made this workload slower at every step, monotonically
-- 1 worker processed 587 tiles/second; 8 workers processed 22.** This
reproduces the scaling benchmark's own finding exactly (same monotonic pattern, same
order of magnitude), not a regression: `multiprocessing` on Windows
uses `spawn`, so every additional worker pays a real multi-second cost
starting a fresh interpreter and re-importing `numpy`/`xgboost`/
`scikit-learn`/`rasterio` before doing any of this workload's genuinely
small amount of real compute (`total_cpu_seconds` stays under 14s even
at 8 workers, while wall time reaches 22s). `docs/bottleneck-
identification.md` already named this exact cost as the
pipeline's real bottleneck; this run is further, independent
confirmation of it, not a new finding.

## Failure and recovery

`data/processed/distributed/fault_injection_report.json`, 500 tiles, 4
workers, one worker's process genuinely killed (`os._exit(1)`) mid-chunk:

```text
any_failure_detected:            true
all_chunks_eventually_succeeded: true
total_tiles_recovered:           500 / 500
total_recovery_seconds:          1.353

chunk 0 (killed):  attempts=2  failure_detected=true   result=OK
chunk 1:           attempts=1  failure_detected=false  result=OK
chunk 2:           attempts=1  failure_detected=false  result=OK
chunk 3:           attempts=1  failure_detected=false  result=OK
```

**A killed worker cost this workload 1.35 real seconds and zero lost
tiles.** Detection, retry, and terminal-state correctness match the
fault-injection test's original run exactly; recovery time (1.353s here vs 1.154s
originally) varies run to run for the documented reason in
`docs/fault-injection-test.md` -- the replacement worker pays the same
real cold-start cost the scaling numbers above show, so recovery time
is not a fixed constant.

**Achieved zero lost tiles after a real killed worker, recovering in
1.35 seconds, at the same process-spawn cost that also makes adding
workers slower on this platform.**

## What this task does not do

- **Does not change `distributed/scaling.py`, `distributed/run.py`,
  `distributed/fault_tolerance.py`, or either runner script.** All four
  are on the `benchmark-v1` frozen list; this task only re-runs them.
- **Does not investigate a fix for the spawn-overhead finding.**
  `docs/multi-worker-scaling.md` already scopes that as a real, open
  question (a persistent pool, threads, or a fork-based Linux target)
  outside what this benchmark work's own job is: measuring and reporting the
  real number honestly, not redesigning around it.
