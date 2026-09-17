# Distributed Result Demo — LOCKED

This document records the distributed result demo. It is not
a brainstorming document. It presents the actual 1/2/4/8-worker
benchmark table the handbook asks for -- already measured twice,
independently, in this project (once for the final distributed
benchmark and once for the clean-clone reproduction), not re-run a
third time to restate the same real numbers.

## The table

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

(`docs/distributed-benchmark.md`.)

## Reproduced independently

Run again from a genuinely fresh clone with no shared state
(`docs/clean-clone-test.md`):

```text
workers   wall_s    speedup   efficiency
      1    0.879      1.000        1.000
      2   11.326      0.078        0.039
      4   12.453      0.071        0.018
      8   18.666      0.047        0.006
```

Same shape both times: 1 worker is fastest, and every additional
worker makes the workload slower, monotonically. The exact wall-clock
seconds differ run to run (real process-spawn timing on a shared
machine varies), but the pattern -- and the conclusion it supports --
does not: **this workload's real compute is small enough that Windows'
per-process `spawn` cold-start cost dominates at every worker count
tested**, the same finding `docs/bottleneck-identification.md`
named directly.

## What this task does not do

- **Does not re-run the benchmark a third time.** Two independent real
  runs, on two different machines' worth of state (this repo's working
  copy, and a from-scratch clean clone), already establish the pattern
  is reproducible; a third run would not add evidence.
- **Does not reinterpret the result as a regression or a bug.**
  `docs/multi-worker-scaling.md` and `docs/distributed-benchmark.md`
  both already establish this is the correct, honestly-reported answer
  for this fixed workload and platform, not something to redesign
  around for this demo.
