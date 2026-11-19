# Serving the Forecast Model on a GPU

The forecast API scores the calibrated XGBoost model on the CPU. This
page measures whether a GPU, and scoring several requests together,
lets one server handle more requests per second while latency stays
low. The changes and their success criteria below were written before
any of the runs.

## Setup

| Item | Choice |
|---|---|
| Model | The production model (`production_model_v1`): XGBoost with 130 trees of depth 4 and isotonic calibration, in the portable JSON format of the [daily map](daily-risk-map.md) |
| Requests | 256 cells each, about one region. Each request takes 256 neighboring rows, from a random start, from the 19,950 rows of two 2025 cutoffs (August 3 and August 10). The features are ready, as if read from a feature store; building them is not timed. |
| Server | One worker thread scores requests from a queue (`serving/batching.py`). With batching, it takes the first waiting request, then waits up to 2 ms for more, up to 64 requests (16,384 rows), and scores them in one call. |
| Load | Open loop: requests arrive at random (Poisson) times at a fixed average rate for 10 s, whether or not the server keeps up. The rates are 25, 50, 100 and so on, doubling up to 6,400 per second. A setup stops at the first rate it fails. |
| Latency | From each request's planned arrival time to the end of its scoring, so a late load generator or a long queue counts against the server |
| Service level | The 99th percentile of latency (p99) is at most 100 ms, and at least 95% of the generated requests per second are completed. The highest rate that meets both is the setup's capacity. |
| Machine | Kaggle with 4 CPU cores and one Tesla T4. The CPU setups use all 4 cores. |
| Repeats | Each setup runs twice, in reverse order the second time |

Before the load test, the scores of each device are compared with the
CPU scores saved when the inputs were exported, and the time to score
1 to 64 requests in one call is measured.

## Changes and success criteria

| # | Change | Success criterion |
|---|---|---|
| 1 | Score on the GPU instead of the CPU, one request at a time | The capacity is at least 1.5 times the CPU's in both runs, and every score is within 0.00001 of the saved scores |
| 2 | Batching on the GPU | The capacity is at least 2 times the GPU's capacity with one request at a time in both runs, and the median latency at 25 requests per second is at most 5 ms higher |
| 3 | The same batching on the CPU | The capacity is at least 1.5 times the CPU's capacity with one request at a time in both runs |

## Results

Run with `notebooks/serving_on_t4.ipynb` on Kaggle
(`ml/artifacts/serving/`): Tesla T4, 4 CPU cores, XGBoost 3.4.1.

**Accuracy.** On all 19,950 rows, the CPU scores matched the saved scores
exactly. The GPU scores differed by up to 0.0000299, about three times
the 0.00001 tolerance, so the GPU setups fail their criteria whatever
their speed.

**Time to score one call:**

| Requests in one call | Rows | CPU (ms) | GPU (ms) |
|---:|---:|---:|---:|
| 1 | 256 | 0.58 | 1.15 |
| 4 | 1,024 | 1.29 | 1.32 |
| 16 | 4,096 | 5.20 | 2.09 |
| 64 | 16,384 | 15.01 | 5.35 |

**Load test**, both runs:

| Setup | Capacity (requests/s) | Median latency at 25/s (ms) | Median and p99 latency at capacity (ms) | Kept |
|---|---:|---:|---|---|
| CPU, one at a time | 800 | 1.0 to 1.1 | 1.2 and 4.2 to 5.9 | – |
| 1. GPU, one at a time | 800 | 1.6 | 6.0 to 7.4 and 43.1 to 45.0 | No |
| 3. CPU, batching | **3,200** | 3.1 | 13.0 to 13.9 and 45.4 to 57.3 | **Yes** |
| 2. GPU, batching | **6,400 or more** | 3.7 | 8.2 to 8.3 and 16.1 to 25.0 | No |

What this shows:

- **Batching on the CPU met its criterion.** It handled 3,200 requests
  per second in both runs, 4 times the 800 of one request at a time, for
  about 2 ms more median latency at low load. At 6,400 per second it
  completed about 4,200, close to the 4,260 that the 15.0 ms for 64
  requests allows.
- **The GPU does not help one request at a time.** Each call costs at
  least 1.15 ms, about twice the CPU's 0.58 ms for one request, so the
  GPU also reached only 800 per second. At 1,600 per second it completed
  about 910, close to the 870 that 1.15 ms per call allows.
- **The GPU with batching was the fastest setup but failed on
  accuracy.** It held the highest rate tested, 6,400 per second, with a
  p99 of 16 to 25 ms, 8 times its capacity without batching, and its
  median latency at low load was 2.1 ms higher. It met the speed parts
  of its criterion, but its scores were outside the tolerance, so it
  was not kept.
- **At 6,400 requests per second the GPU was busy only about 13% of the
  time**, at its idle clock of 585 MHz. The limit there is the Python
  server and the CPU work around each call, not the GPU. Its real
  capacity is above the rates that were tested.
- **Scoring is a small model.** With 130 shallow trees, one call on 256
  rows is shorter than the GPU's fixed cost per call. The GPU pays off
  only when many requests are scored together.

The forecast API keeps scoring on the CPU. Batching on the CPU met its
criterion, but the API does not batch requests yet.

## Limits

- The server and the load generator run in one Python process on 4
  CPU cores, so at high rates they compete for the CPU. HTTP is not
  part of the test.
- One request size (256 cells) and one model. A larger model would
  change the balance between the CPU and the GPU.
- The GPU setup with batching never reached its limit, because 6,400
  requests per second was the highest rate in the plan.

## How to run

Export the model and the feature rows (needs the 2025 dataset and the
production model):

```bash
PYTHONPATH=ml/src python scripts/research/export_serving_inputs.py
```

Then run `notebooks/serving_on_t4.ipynb` on Kaggle with a copy of the
repository that includes `ml/artifacts/serving_inputs/`, and copy its
output to `ml/artifacts/serving/`.

## Code

| File | Purpose |
|---|---|
| `serving/scorer.py` | Scores feature rows with the portable model on the CPU or the GPU |
| `serving/batching.py` | The request queue and batching worker, the open-loop load generator and the latency summary |
| `scripts/research/export_serving_inputs.py` | Saves the model, the feature rows and their CPU scores |
| `scripts/research/run_serving_benchmark.py` | Measures accuracy and scoring times, runs the load test and applies the success criteria |
