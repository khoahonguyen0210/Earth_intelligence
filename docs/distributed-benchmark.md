# Final Distributed Benchmark

This benchmark compares 1, 2, 4 and 8 workers on runtime, throughput,
speedup, efficiency, and failure and recovery. Unlike the ML and
ablation benchmarks, it never needed fire history. The scaling
benchmark (`docs/multi-worker-scaling.md`) and the fault-injection test
(`docs/fault-injection-test.md`) measure compute cost on a fixed
workload. This run repeats both frozen scripts,
`scripts/distributed/run_scaling_benchmark.py` and
`run_fault_injection_test.py` (both on the `benchmark-v1` list), without
changes, to confirm the numbers on the final code. It also reports all
the measures in one place.

## Runtime, throughput, speedup, efficiency

`data/processed/distributed/scaling_benchmark.json`, 500 tiles, with
the same fitted model and loaded data for every row:

```text
workers   actual   wall_s    throughput(tiles/s)  cpu_s    peak_mb   speedup   efficiency
      1        1    0.851               587.49     1.14      1.81      1.000       1.000
      2        2    9.488                52.70      2.61      1.66      0.090       0.045
      4        4   12.109                41.29      5.58      1.61      0.070       0.018
      8        8   22.381                22.34     13.72      1.58      0.038       0.005
```

**Each added worker made this workload slower. One worker processed
587 tiles per second; eight workers processed 22.** This repeats the
earlier scaling result (the same steady decline, at the same order of
magnitude), so it is not a regression. On Windows, `multiprocessing`
uses `spawn`. Each extra worker spends several seconds starting a new
interpreter and importing `numpy`, `xgboost`, `scikit-learn` and
`rasterio` again before it does any of the small compute in this
workload. `total_cpu_seconds` stays under 14 s even with 8 workers,
while wall time reaches 22 s. `docs/bottleneck-identification.md`
names this start-up cost as the bottleneck, and this run confirms it.

## Failure and recovery

`data/processed/distributed/fault_injection_report.json`, 500 tiles, 4
workers, one worker process killed (`os._exit(1)`) during its chunk:

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

**A killed worker cost 1.35 seconds and no lost tiles.** Detection,
retry and the final states match the first fault-injection run. The
recovery time (1.353 s here, 1.154 s in the first run) changes from run
to run for the reason given in `docs/fault-injection-test.md`: the
replacement worker pays the same start-up cost shown in the scaling
table, so recovery time is not a constant.

In summary, no tiles were lost after a worker was killed, and recovery
took 1.35 seconds. The cost of starting a process explains both the
recovery time and the slowdown from adding workers on this platform.

## Out of scope

- **The benchmark code is unchanged.** `distributed/scaling.py`,
  `distributed/run.py`, `distributed/fault_tolerance.py` and both
  runner scripts are on the `benchmark-v1` frozen list, and this run only
  executes them.
- **No fix for the start-up cost is tried here.**
  `docs/multi-worker-scaling.md` lists the options (a persistent pool,
  threads, or a Linux target with `fork`) as open work. This benchmark
  measures and reports the numbers; it does not redesign the system.
