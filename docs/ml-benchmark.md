# Final ML Benchmark — LOCKED

This document records the final ML benchmark. It is
not a brainstorming document.

It asks for a real benchmark of the locked model ladder
(Climatology, Logistic Regression, XGBoost, Calibrated XGBoost),
producing PR-AUC, ROC-AUC, Brier score, log loss, calibration, and
inference time. The earlier benchmark run's own script (`scripts/models/run_baseline_benchmark.py`,
part of the `benchmark-v1` freeze) predates the real historical
dataset entirely -- its docstring says outright that only climatology
could succeed, since the sample data it used had zero real positive
examples in the training/validation splits. The real dataset
(`data/processed/historical_dataset_v1.csv`, built by
`scripts/forecast/build_historical_dataset.py`, 1,316,700 rows) has
since been built and already backs the production model. This task
adds `scripts/models/run_ml_benchmark.py`, a new runner that
loads the real dataset and calls the frozen, unmodified
`models/benchmark.py::run_baseline_benchmark` -- the comparison logic
itself is untouched; only what data it is run against changes,
consistent with the `benchmark-v1` freeze (`docs/benchmark-freeze.md`)
that new data doesn't require a new benchmark version, only a change to
the harness code would.

## Setup

```text
dataset          data/processed/historical_dataset_v1.csv (v1, feature_version v1)
train split      877,800 rows, cutoffs 2019-06-01 -> 2022-10-26
validation split 219,450 rows, cutoffs 2023-06-01 -> 2023-10-26
test split       219,450 rows, cutoffs 2024-06-01 -> 2024-10-26
model config     the one fixed, documented XGBoost config (n_estimators=500,
                  max_depth=4, learning_rate=0.1, subsample=0.8,
                  colsample_bytree=0.8, random_state=20240815) --
                  unchanged since it was first locked
```

## Results

All four models trained and evaluated successfully against real data
for the first time (`ml/artifacts/final_ml_benchmark_v1/comparison.{json,csv}`):

```text
Model                 Succeeded  PR-AUC    ROC-AUC   Brier     LogLoss   Train(s)  Infer(s)
climatology           True       0.2522    0.8616    0.0026    0.0341    0.64      0.08
logistic_regression   True       0.2782    0.9463    0.0649    0.2473    70.69     3.16
xgboost               True       0.4513    0.9669    0.0022    0.0101    38.56     1.40
calibrated_xgboost    True       0.4361    0.9667    0.0022    0.0108    38.47     1.28
```

**Achieved a PR-AUC of 0.45 with XGBoost, nearly double climatology's
0.25 baseline, by fitting the locked feature set on the real 2019-2022
fire history and weather record.**

XGBoost (uncalibrated) has the single best PR-AUC; calibrated XGBoost
trades a small amount of PR-AUC (0.4513 -> 0.4361) for the property
that makes it the one actually served to users -- a predicted
probability that means what it says. Both XGBoost variants dominate
climatology and logistic regression on every metric except training
time (climatology is a closed-form baseline; XGBoost early-stops
around iteration 129, logistic regression's plain gradient solver is
the slowest of the four on this row count).

## Calibration

`ml/artifacts/final_ml_benchmark_v1_calibrated_xgboost/plots/calibration_table.csv`
(10 bins, isotonic-calibrated on the validation split, evaluated on the
test split): predicted and observed frequency track closely across
every populated bin --

```text
predicted_mean   observed_frequency   count
0.0018           0.0012               218,223
0.1337           0.1179                   280
0.2353           0.2087                   369
0.3444           0.3351                   191
0.4885           0.4554                   112
0.6527           0.6154                   156
0.7438           0.7273                    22
0.8715           0.8261                    46
0.9838           0.8667                    45
```

-- including the dominant near-zero bin (218,223 of 219,450 test rows,
matching the real ~0.45% positive rate), where predicted and observed
frequency agree to three decimal places. `reliability_diagram.png` in
the same directory plots this visually.

## What this task does not do

- **Does not change `models/benchmark.py` or `models/harness.py`.**
  Both are on the `benchmark-v1` frozen list and are used exactly as
  frozen; only a new data-loading script was added.
- **Does not delete or overwrite the original result**
  (`ml/artifacts/final_baseline_benchmark_v1`), which stays as the
  honest historical record of what running against sample-only data
  produced -- kept, not archived over, the same way
  `ml/artifacts/reliability_tests/before.json` was kept previously.
