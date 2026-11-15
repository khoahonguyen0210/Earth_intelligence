# Distributed Result Demo

This demo presents the 1, 2, 4 and 8-worker benchmark table. It was
measured twice, separately: once for the final distributed benchmark
and once in the clean-clone test. It is not run a third time.

## Table

```bash
python scripts/distributed/run_scaling_benchmark.py
```

```text
workers   wall_s    throughput(tiles/s)   speedup   efficiency
      1    0.851               587.49       1.000       1.000
      2    9.488                52.70       0.090       0.045
      4   12.109                41.29       0.070       0.018
      8   22.381                22.34       0.038       0.005
```

Source: `docs/distributed-benchmark.md`.

## Reproduced separately

Run again from a new clone with no shared state
(`docs/clean-clone-test.md`):

```text
workers   wall_s    speedup   efficiency
      1    0.879      1.000        1.000
      2   11.326      0.078        0.039
      4   12.453      0.071        0.018
      8   18.666      0.047        0.006
```

Both runs have the same shape: 1 worker is fastest, and each added
worker makes the workload slower. The exact seconds differ between runs,
because process start-up time varies on a shared machine, but the
pattern and the conclusion do not. **The compute in this workload is so
small that the cost of starting each process with Windows `spawn` is
larger at every worker count tested.** `docs/bottleneck-identification.md`
measures this directly.

## Notes

- **The benchmark is not run a third time.** Two separate runs, one in
  the working copy and one in a new clean clone, already show that the
  pattern repeats. A third run would add no evidence.
- **The result is not a regression or a bug.**
  `docs/multi-worker-scaling.md` and `docs/distributed-benchmark.md`
  both explain that this is the correct result for this fixed workload
  and platform.
