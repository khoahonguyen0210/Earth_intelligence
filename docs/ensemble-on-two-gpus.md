# Ensemble Forecasts on Two GPUs

One weather forecast shows one possible future. An ensemble runs the
same model many times from slightly different starting states, and the
spread of its members shows how certain the forecast is. Each member
costs a full forecast, so an ensemble is a throughput problem: how many
members per minute one GPU, or two GPUs, can run.

This page measures that throughput for SFNO on Kaggle's two T4 GPUs.
The changes and their success criteria below were written before any of
the runs.

## Setup

| Item | Choice |
|---|---|
| Model | SFNO with the memory changes in [Earth-2 Models on a T4](earth2-models-on-t4.md#fitting-sfno-on-a-t4) |
| Start | ERA5 from ARCO at 2025-08-03 06:00 UTC (cutoff 10:00 UTC), the date of the [pipeline runs](daily-risk-map.md#pipeline-profile) |
| Forecast | 11 steps of 6 hours per member, with the daily values over California computed as in the daily run |
| Members | 8. Member 0 is the control and is not changed. Every other member adds Gaussian noise with 5% of each variable's spatial standard deviation, drawn from its own seed (20261118 plus the member number). |
| Batches | A batch runs several members through the model in one call, along a new `ensemble` dimension, as Earth2Studio's own ensemble workflow does |
| Two GPUs | One worker process per GPU, each with its own copy of the model. The members are split evenly (0 to 3 and 4 to 7). The initial state is downloaded once and shared through a file. |
| GPU activity | NVML reads each GPU every 0.2 s: utilization, SM clock, temperature, power and memory |

The noise only creates a realistic workload. It is not a calibrated
ensemble, so its spread is not a measure of forecast uncertainty.

Each member's noise comes from its own seed, so a member gives the same
numbers whichever batch or GPU runs it. This makes all runs directly
comparable.

## Measures

- **Forecast time**: from the start of the first member to the end of
  the last one, over all GPUs. Loading the model is reported separately.
- **Members per minute**: 8 divided by the forecast time.
- **Warm throughput**: member-steps per second without each worker's
  first batch, which includes one-time GPU setup.
- **Peak memory**: the most GPU memory allocated in any batch, next to
  the memory that the model alone uses.

## Changes and success criteria

| # | Change | Why it could help | Success criterion |
|---|---|---|---|
| 1 | Run 2 members per batch on one GPU | Larger inputs give larger kernels, which can keep the GPU busier | It fits in memory, its warm throughput is at least 10% higher than batch 1 against both batch-1 runs, and every member is within the forecast tolerance of the batch-1 run |
| 2 | Run 4 members per batch on one GPU | As above | As above |
| 3 | Split the members over two GPUs, batch 1 | The members are independent, so two GPUs could take half the time | The forecast time is at most 55% of the one-GPU time (at least 1.8 times the speed) against both one-GPU runs, and every member is identical to the one-GPU run |

The forecast tolerance is the one in
[Daily Risk Map](daily-risk-map.md#pipeline-changes): every value within
0.01 + 0.001 × |value| of the reference, with missing values in the same
cells.

Two checks are reported but are not criteria:

- The control member is compared with the E7 forecast for the same date
  (`ml/artifacts/e7_forecasts/forecast_20250803T10.npz`).
- The spread of the members' daily index values must be above zero, to
  show that the noise reaches the forecast.

The runs take turns in this order: one GPU with batch 1, batch 2, two
GPUs, then the same three again, then batch 4 once. The batch-1 and
two-GPU runs are repeated because two identical pipeline runs differed
by up to 9 s.

## Results

Run with `notebooks/ensemble_on_t4.ipynb` on Kaggle
(`ml/artifacts/ensemble_on_t4/`): two Tesla T4 GPUs with a 70 W power
limit, 4 CPU cores, PyTorch 2.11.0, Earth2Studio 0.20.0.

| Run | Forecast time for 8 members (s) | Members per minute | Warm throughput (member-steps/s) | Peak memory (GB) | Kept |
|---|---:|---:|---:|---:|---|
| One GPU, batch 1, run 1 | 223.2 | 2.15 | 0.411 | 13.06 | – |
| One GPU, batch 1, run 2 | 230.2 | 2.09 | 0.386 | 13.06 | – |
| 1. One GPU, batch 2, run 1 | 229.5 | 2.09 | 0.384 | 13.98 | No |
| 1. One GPU, batch 2, run 2 | 232.5 | 2.06 | 0.383 | 13.98 | No |
| 2. One GPU, batch 4 | Out of memory | – | – | – | No |
| 3. Two GPUs, batch 1, run 1 | 120.3 | 3.99 | 0.778 | 13.06 | Yes |
| 3. Two GPUs, batch 1, run 2 | 118.9 | 4.04 | 0.771 | 13.06 | Yes |

GPU activity during the forecasts, from NVML:

| Run | Busy | Mean SM clock (MHz) | Mean power (W) | Highest temperature (°C) |
|---|---:|---:|---:|---:|
| One GPU, batch 1 | 94% to 98% | 729 to 821 | 64.8 to 65.7 | 77 to 78 |
| One GPU, batch 2 | 98% | 713 to 731 | 65.7 to 65.9 | 78 |
| Two GPUs, batch 1 (each GPU) | 94% to 96% | 726 to 787 | 64.5 to 65.6 | 78 to 79 |

What this shows:

- **Two GPUs nearly halve the forecast time.** The two-GPU runs took
  51.6% to 53.9% of the one-GPU time, 1.86 to 1.94 times the speed, and
  met their criterion. Every member was identical to the one-GPU run.
- **They do not reach 2 times the speed** because the first member on
  each GPU includes one-time GPU setup (29.6 to 35.9 s, against 24.5 to
  30.8 s for the others). With 4 members per GPU, this cost weighs more
  than with 8. GPU 1 also ran at a higher clock than GPU 0 (784 to
  787 MHz against 726 to 727 MHz).
- **With model loading included**, a run took 150.0 to 151.5 s on two
  GPUs and 253.7 to 263.0 s on one, 1.68 to 1.75 times the speed. Each
  worker loads its own copy of the model in 23 to 28 s.
- **Batching does not help.** With one member, the GPU is already busy
  94% to 98% of the time. With two members per batch, each pair took
  57.2 to 60.4 s, the same time per member as one at a time. The warm
  throughput was 0.6% to 6.8% lower, so batch 2 missed its criterion.
- **Four members do not fit.** The model alone uses 2.75 GB, one member
  13.06 GB at the peak, and each further member about 0.92 GB more. With
  four members, the run needed another 1.49 GiB when 13.22 GiB were in
  use on a 14.56 GiB GPU.
- **The T4 runs at its power limit.** It drew about 65 W of its 70 W,
  and its clock averaged 713 to 821 MHz, about half of its 1,590 MHz
  maximum. As it warmed up, members took longer: in the first one-GPU
  run, 24.5 s for the second member and 28.5 s for the last. This
  probably explains part of the differences between identical runs.

Checks:

- **The control member was identical to the E7 forecast** for the same
  date in every finished run, so the batched path computes the same
  values as the original one.
- **The members differ from each other.** The median spread of the
  daily highest index was 12.7, 8.3 and 6.6 on day +1, +2 and +3. The
  spread falls with lead time, unlike a calibrated ensemble, likely
  because the model smooths out the grid-point noise. This setup
  measures throughput only.

## Limits

- One date, 8 members and two repeats of each setting.
- The members are independent, so the GPUs never exchange data. This
  does not test training or splitting one model over several GPUs.
- Kaggle machines are shared, and the T4 slows down as it heats up, so
  the times vary between runs.

## How to run

Run `notebooks/ensemble_on_t4.ipynb` on Kaggle with two T4 GPUs and copy
its output to `ml/artifacts/ensemble_on_t4/`. Then compare the runs:

```bash
PYTHONPATH=ml/src python scripts/research/compare_ensemble_runs.py \
  ml/artifacts/ensemble_on_t4 \
  --forecast ml/artifacts/e7_forecasts/forecast_20250803T10.npz
```

## Code

| File | Purpose |
|---|---|
| `earth2/ensemble.py` | Noise per member, batched forecasts, daily values per member, saving and merging |
| `earth2/gpu_monitor.py` | Reads GPU activity from NVML in a background thread |
| `scripts/research/run_ensemble.py` | Downloads the initial state once, starts one worker per GPU and merges their members |
| `scripts/research/compare_ensemble_runs.py` | Compares the runs and applies the success criteria |
