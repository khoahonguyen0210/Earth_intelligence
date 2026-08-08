# Bottleneck Identification — LOCKED

This document freezes bottleneck identification per Task 9.4 of the
Execution Handbook. It is not a brainstorming document. It explains,
with direct real measurements rather than inference, why
`docs/multi-worker-scaling.md` (Task 9.3) found more workers making the
workload monotonically slower.

## The implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/bottleneck.py
scripts/distributed/run_bottleneck_report.py
```

Task 9.3's numbers alone only show *that* more workers were slower, not
*which* of the handbook's six candidate factors (CPU, I/O, network,
database, serialization, coordination) caused it. This task isolates
each candidate with its own direct measurement rather than guessing from
aggregate wall-clock numbers:

```text
cpu           -- Task 9.2's own real per-tile compute time
                 (DistributedRunResult.total_cpu_seconds)
i_o           -- Task 9.2's own real data-loading stage time
                 (RunContext.data_loading)
serialization -- pickling one real ChunkTask directly (the exact object
                 multiprocessing.Pool.map sends across the process
                 boundary), not inferred from a Pool run
coordination  -- starting a real Pool(n) whose workers do nothing at all
                 (measure_spawn_overhead) -- isolates pure process-spawn
                 cost with zero real work mixed in
network       -- never reached: nothing in this pipeline makes a network
                 call
database      -- never reached: nothing in this pipeline makes a
                 database call
```

`network`/`database` are correctly absent from the real measurements,
not candidates this task forgot to check -- the whole pipeline (data
loading, feature building, model inference) is pure in-process Python
plus local `multiprocessing`.

## Result

A real run of `scripts/distributed/run_bottleneck_report.py`:

```text
real_compute_seconds:   1.078
data_loading_seconds:   9.359
serialization_seconds:  0.953  (5,234,869 bytes per single-tile task)
spawn_overhead[1]:      0.000
spawn_overhead[2]:      8.175
spawn_overhead[4]:     13.846
spawn_overhead[8]:     24.882

DOMINANT FACTOR: coordination
```

**Coordination (process-spawn overhead) is the real bottleneck, proven
directly, not inferred.** 8 *empty* workers -- doing zero real work --
already cost 24.9 seconds just to start, which alone exceeds the
entire real computational workload (1.08 seconds of CPU across all 500
tiles) by more than 20x. This is the direct, isolated confirmation of
what Task 9.3's aggregate numbers already implied: adding workers adds
this same fixed per-process startup cost (Windows' `spawn` start method
re-launching a Python interpreter and re-importing the whole `ml`
package -- numpy, xgboost, scikit-learn, rasterio -- from scratch for
every single worker) far faster than it adds any usable parallel
compute capacity, because there is so little real compute here to
parallelize in the first place.

## A real secondary finding: serialization is not negligible either

5.2MB pickled per single-tile task is entirely the shared
observations/era5_records/geography_cells/model every `ChunkTask`
currently carries in full, regardless of how many tiles that chunk
actually covers (`docs/one-worker-baseline.md`'s own documented design).
At 8 workers, that is a real ~42MB moved across process boundaries
before any of them does a single tile's worth of work -- a real,
measured cost, and a concrete lead for anyone optimizing this pipeline
later (shipping only each chunk's already-filtered relevant records,
not the shared full dataset, to each worker).

## Why this does not change Task 9.3's numbers or conclusion

This task explains the mechanism; it does not re-run or revise the
scaling benchmark. The fix this measurement points to -- a persistent
worker pool reused across many workloads (amortizing spawn cost over
many calls instead of paying it once per benchmark run), or a
Linux/fork-based deployment target where `fork` avoids re-importing the
whole interpreter -- is real follow-up work, not something this
diagnostic task does itself.

## Result artifact

```text
data/processed/distributed/bottleneck_report.json
```

Gitignored, regenerable, like every other `data/processed/` artifact in
this project.

## What this document does not define

Whether a fork-based or persistent-pool redesign would actually change
Task 9.3's scaling numbers is a real, open, untested question -- this
task only names the cause on the current implementation and platform,
it does not build or measure an alternative one.
