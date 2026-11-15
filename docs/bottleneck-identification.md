# Bottleneck Identification

`docs/multi-worker-scaling.md` found that each added worker made the
workload slower. This document measures each possible cause directly to
find out why.

## Implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/bottleneck.py
scripts/distributed/run_bottleneck_report.py
```

The scaling numbers show that more workers were slower, but not which
of six possible causes was responsible: CPU, I/O, network, database,
serialization or coordination. Each cause gets its own measurement:

```text
cpu            the per-tile compute time
               (DistributedRunResult.total_cpu_seconds)
i_o            the data-loading stage time
               (RunContext.data_loading)
serialization  pickling one ChunkTask directly (the same object that
               multiprocessing.Pool.map sends to a worker process)
coordination   starting a Pool(n) whose workers do nothing
               (measure_spawn_overhead), which isolates the cost of
               starting processes
network        not measured: the pipeline makes no network calls
database       not measured: the pipeline makes no database calls
```

Network and database are left out because the whole pipeline (data
loading, feature building, model inference) runs in-process with local
`multiprocessing`.

## Result

A run of `scripts/distributed/run_bottleneck_report.py`:

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

**Coordination, the cost of starting worker processes, is the
bottleneck.** Eight workers that do nothing take 24.9 seconds to start.
That is more than 20 times the whole compute workload, which is 1.08
seconds of CPU across all 500 tiles. On Windows, the `spawn` start
method launches a new Python interpreter for every worker and imports
the whole `ml` package again (numpy, xgboost, scikit-learn, rasterio).
Each added worker adds this fixed cost, and there is too little compute
to gain anything from running it in parallel.

## Second finding: serialization also costs time

Each single-tile task pickles to 5.2 MB. Almost all of it is the shared
data that every `ChunkTask` carries in full (observations,
era5_records, geography_cells and the model), however few tiles the
chunk covers. This design is described in
`docs/one-worker-baseline.md`. With 8 workers, about 42 MB moves between
processes before any tile is computed. Sending each worker only the
records for its own chunk would reduce this.

## Effect on the scaling results

This report explains the cause. It does not rerun or change the scaling
benchmark. Two changes could reduce the cost: a worker pool that stays
alive across many workloads, so the start-up cost is paid once, or a
Linux deployment where `fork` avoids importing everything again. Both
are follow-up work.

## Result file

```text
data/processed/distributed/bottleneck_report.json
```

Like every file under `data/processed/`, it is ignored by git and can
be rebuilt.

## Open question

Whether a fork-based or persistent pool would change the scaling
numbers has not been tested. This report names the cause for the
current code on the current platform only.
