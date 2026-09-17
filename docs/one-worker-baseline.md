# One-Worker Baseline — LOCKED

This document freezes the one-worker distributed-inference baseline.
It is not a brainstorming document. It runs `docs/distributed-workload.md`'s
frozen workload exactly as fixed; later multi-worker scaling work reuses
this same implementation with a different worker count rather than
reimplementing it, so the two are a genuine apples-to-apples comparison.

## The implementation

```text
ml/src/ai_earth_intelligence_and_forecasting_engine/distributed/run.py
scripts/distributed/run_baseline.py
```

`run_distributed_inference(workload, num_workers, ...)` is the one real
function both this baseline (`num_workers=1`) and the multi-worker
scaling benchmark (`num_workers=2/4/8`) call. It:

```text
1. Loads the real sample data once (timed as its own stage).
2. Fits the one calibrated-XGBoost model the whole run holds fixed
   (fit_baseline_model), from a fixed 100-cell set independent of the
   inference workload size.
3. Splits the workload's 500 tile_ids into `num_workers` near-equal
   contiguous chunks.
4. Dispatches each chunk to a worker (multiprocessing.Pool) that builds
   real feature rows for its tiles and scores them with the fitted
   model -- this is the real, measured unit of distributed work.
5. Measures wall time, CPU time (summed across workers), peak memory
   (max across workers), and throughput.
```

## Why model-fitting needed its own documented fallback

This was already flagged earlier: no earlier task ever persisted a
trained model object (`ml/artifacts/calibrated_xgboost_v1/` holds only a
config and a README). Fitting one fresh here hits the exact gap
`profiling.py` already documented and solved: the real train/validation
splits have zero real historical positive examples in this project's
small sample data, so `fit_calibration` (which needs both classes
present in validation) raises. `fit_baseline_model` reuses that same
fallback (`models.profiling.synthetic_timing_rows`, promoted from a
private helper to a shared public one for this reuse) rather than
inventing a second one: realistically-shaped, both-classes-present rows
used only to measure computational cost, never to report an accuracy
number. The real run below hit this fallback, as expected
(`used_synthetic_model_fallback: true`).

## Why the inference step still uses real data despite that

The model-fitting fallback only affects the one-time setup cost
(excluded from the per-worker measurement). The actual measured
workload -- building feature rows for 500 real California grid tiles
from the real FIRMS/ERA5/geography sample files, then scoring them --
runs on real data and real code paths throughout. The sample geography
file only covers a small fixed bounding box (`scripts/query/
run_forecast_cli.py`'s `GEOGRAPHY_BBOX`), so most of the workload's 500
tiles (drawn from the full California grid, not that one bounding box)
get no geography match -- `DatasetRow`'s geography fields are nullable
for exactly this reason, and every other real join and the real
prediction call still execute in full. This benchmark measures
computational cost, not feature completeness.

## Result

A real run of `scripts/distributed/run_baseline.py` (500 tiles, 1
worker):

```text
wall_seconds:         1.684
throughput_tiles_per_second: 296.963
total_cpu_seconds:    0.734
peak_memory_mb:       1.810
data_loading:         21.997 seconds (a one-time setup cost, not part
                       of the per-worker measurement above)
used_synthetic_model_fallback: true
```

Saved to `data/processed/distributed/one_worker_baseline.json`
(gitignored, regenerable, like every other `data/processed/` artifact
in this project).

The one-time data-loading stage (~22s, dominated by parsing the sample
ERA5 NetCDF file and the sample DEM/land-cover rasters) is over an
order of magnitude slower than the entire 500-tile inference workload
it precedes (1.68s). This is itself a real, measured finding worth
carrying into later bottleneck-identification work: for this workload
size, I/O-bound one-time setup, not CPU-bound per-tile computation, is
where the real time goes -- a fact a naive read of "500 tiles took 1.68
seconds" alone would hide.

## What this document does not define

The multi-worker scaling work varies only `num_workers` against this
exact same implementation and workload to compute real speedup/
efficiency numbers; this document's job was only to establish the
`num_workers=1` reference point those numbers are measured against.
