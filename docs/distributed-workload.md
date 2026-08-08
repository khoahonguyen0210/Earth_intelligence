# Distributed Workload — LOCKED

This document freezes the distributed geospatial workload per Task 9.1
of the Execution Handbook, the first task of Phase 9. It is not a
brainstorming document. Tasks 9.2-9.5 (one-worker baseline, multi-worker
scaling, bottleneck profiling, fault injection) all run against this
exact workload rather than each defining their own.

## The fixed workload

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/workload.py
```

```text
grid_version:    v1   (Task 1.6's data.grid.GRID_VERSION)
dataset_version: v1   (Task 3.7's forecast.build_dataset.DATASET_VERSION)
feature_version: v1   (Task 3.7's forecast.build_dataset.FEATURE_VERSION)
model_version:   calibrated_xgboost_v1 (ml/artifacts/calibrated_xgboost_v1/)
workload_size:   500 tiles
tile_ids:        the first 500 tiles of Task 1.6's real California grid,
                 in the grid's own deterministic lat/lon-index order
                 (data.grid.build_california_grid()[:500])
```

500, not the full ~10,000-tile grid: large enough that real parallelism
has something to show (Task 9.3's speedup/efficiency numbers would be
noise on a handful of tiles), small enough that a 1-worker baseline
(Task 9.2) finishes in a reasonable local runtime rather than requiring
a cluster to even establish the baseline.

The first 500 tiles by grid order, not a random sample: reusing the
existing deterministic ordering (already proven stable by Task 1.6's own
tests) is simplest and needs no new seeding/randomness concern -- the
handbook's requirement is a *fixed* batch, not a *representative* one.

## Why version identifiers are reused, not reinvented

`grid_version`/`dataset_version`/`feature_version` are the exact
constants Tasks 1.6/3.7 already locked (`data.grid.GRID_VERSION`,
`forecast.build_dataset.DATASET_VERSION`/`FEATURE_VERSION`), not new
Phase-9-specific strings -- a workload record that named a dataset
version the rest of the project didn't recognize would be a
reproducibility gap, not a convenience. `model_version` is new
(`calibrated_xgboost_v1`) because no earlier task named one: Tasks
4.3/4.4/4.6/5.x each fit calibrated XGBoost fresh in memory for their
own benchmark run and never persisted the trained model object itself
(`ml/artifacts/calibrated_xgboost_v1/` holds only `config.json` and a
`README.md` -- the hyperparameters and the write-up, not a serialized
model). Task 9.2's one-worker baseline is therefore the first task that
needs an actual fitted model object to run repeated inference against,
and it is expected to fit one itself from that same locked config,
holding the fitted model fixed for the duration of one benchmark run
(training itself is not part of what Phase 9 measures).

## Result

```text
ml/artifacts/distributed_workload_v1/workload.json
```

A real, generated record (`scripts/distributed/freeze_workload.py`):
500 real tile ids, the four version identifiers above. Gitignored, like
every other `ml/artifacts/` entry -- regenerable on demand, not tracked
state.

## What this document does not define

Nothing here runs a forecast, measures a runtime, or touches a worker --
that is Task 9.2 onward. This task only fixes *what* every later Phase 9
benchmark must hold constant: the tiles, the dataset, and the model.
