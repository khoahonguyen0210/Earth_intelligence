# One-Worker Baseline

This baseline runs the frozen workload from
`docs/distributed-workload.md` with one worker. The multi-worker
benchmark reuses the same implementation and changes only the worker
count, so the two results compare like with like.

## Implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/run.py
scripts/distributed/run_baseline.py
```

`run_distributed_inference(workload, num_workers, ...)` is the one
function that both this baseline (`num_workers=1`) and the multi-worker
benchmark (`num_workers=2/4/8`) call. It:

```text
1. Loads the sample data once (timed as its own stage).
2. Fits the one calibrated XGBoost model that stays fixed for the
   whole run (fit_baseline_model), from a fixed set of 100 cells that
   does not depend on the size of the inference workload.
3. Splits the workload's 500 tile_ids into `num_workers` chunks of
   nearly equal size, each a continuous range.
4. Sends each chunk to a worker (multiprocessing.Pool) that builds
   feature rows for its tiles and scores them with the fitted model.
   This is the unit of distributed work that is measured.
5. Measures wall time, CPU time (summed over workers), peak memory
   (the maximum over workers) and throughput.
```

## Why model fitting needs a fallback

No earlier step saved a trained model object
(`ml/artifacts/calibrated_xgboost_v1/` holds only a config and a
README). Fitting a new one here hits the gap that `profiling.py`
already documents and handles: in the small sample data, the train and
validation splits have no positive examples, so `fit_calibration`
(which needs both classes in validation) raises an error.
`fit_baseline_model` reuses the same fallback,
`models.profiling.synthetic_timing_rows`, which was made public for
this reuse. The fallback creates rows with a realistic shape and both
classes. They are used only to measure compute cost, never to report
accuracy. The run below used this fallback, as expected
(`used_synthetic_model_fallback: true`).

## Why inference still uses the sample data

The fallback affects only the one-time setup, which is not part of the
per-worker measurement. The measured work, building feature rows for
500 California grid tiles from the FIRMS, ERA5 and geography sample
files and then scoring them, runs on that data and the normal code.
The sample geography file covers only a small fixed bounding box
(`GEOGRAPHY_BBOX` in `scripts/query/run_forecast_cli.py`). Most of the
500 tiles come from the whole California grid, outside that box, so
they get no geography match. The geography fields of `DatasetRow` can be
empty for this reason, and every other join and the prediction call
still run in full. This benchmark measures compute cost, not feature
completeness.

## Result

A run of `scripts/distributed/run_baseline.py` (500 tiles, 1 worker):

```text
wall_seconds:         1.684
throughput_tiles_per_second: 296.963
total_cpu_seconds:    0.734
peak_memory_mb:       1.810
data_loading:         21.997 seconds (a one-time setup cost, not part
                      of the per-worker measurement above)
used_synthetic_model_fallback: true
```

Saved to `data/processed/distributed/one_worker_baseline.json`, which,
like every file under `data/processed/`, is ignored by git and can be
rebuilt.

The one-time data loading (about 22 s, mostly reading the sample ERA5
NetCDF file and the sample elevation and land-cover rasters) takes more
than ten times as long as the whole 500-tile inference that follows it
(1.68 s). At this workload size, most of the time goes to one-time I/O,
not to per-tile computation. The figure "500 tiles took 1.68 seconds"
alone would hide this. `docs/bottleneck-identification.md` follows it
up.

## Out of scope

The multi-worker benchmark changes only `num_workers` on this same
implementation and workload to compute speedup and efficiency. This
document sets only the `num_workers=1` reference point.
