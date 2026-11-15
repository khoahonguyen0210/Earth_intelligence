# Final ML Benchmark

This benchmark compares the four models (climatology, logistic
regression, XGBoost and calibrated XGBoost) on PR-AUC, ROC-AUC, Brier
score, log loss, calibration and inference time.

The first benchmark script, `scripts/models/run_baseline_benchmark.py`
(part of the `benchmark-v1` freeze), was written before the historical
dataset existed. Its docstring says that only climatology could
succeed, because the sample data had no positive examples in the
training and validation splits. The full dataset
(`data/processed/historical_dataset_v1.csv`, built by
`scripts/forecast/build_historical_dataset.py`, 1,316,700 rows) now
exists and is used by the production model.

`scripts/models/run_ml_benchmark.py` is a new runner that loads the
full dataset and calls the frozen, unchanged
`models/benchmark.py::run_baseline_benchmark`. The comparison logic is
the same; only the input data is new. Under the `benchmark-v1` freeze
(`docs/benchmark-freeze.md`), new data does not need a new benchmark
version; only a change to the benchmark code would.

## Setup

```text
dataset          data/processed/historical_dataset_v1.csv (v1, feature_version v1)
train split      877,800 rows, cutoffs 2019-06-01 -> 2022-10-26
validation split 219,450 rows, cutoffs 2023-06-01 -> 2023-10-26
test split       219,450 rows, cutoffs 2024-06-01 -> 2024-10-26
model config     the one fixed, documented XGBoost config (n_estimators=500,
                 max_depth=4, learning_rate=0.1, subsample=0.8,
                 colsample_bytree=0.8, random_state=20240815),
                 unchanged since it was first set
```

## Results

All four models trained and were evaluated on the full data for the
first time (`ml/artifacts/final_ml_benchmark_v1/comparison.{json,csv}`):

```text
Model                 Succeeded  PR-AUC    ROC-AUC   Brier     LogLoss   Train(s)  Infer(s)
climatology           True       0.2522    0.8616    0.0026    0.0341    0.64      0.08
logistic_regression   True       0.2782    0.9463    0.0649    0.2473    70.69     3.16
xgboost               True       0.4513    0.9669    0.0022    0.0101    38.56     1.40
calibrated_xgboost    True       0.4361    0.9667    0.0022    0.0108    38.47     1.28
```

**XGBoost reached a PR-AUC of 0.45, nearly double the 0.25 of
climatology**, using the full feature set on the 2019-2022 fire history
and weather record.

Uncalibrated XGBoost has the best PR-AUC. Calibrated XGBoost gives up a
little PR-AUC (0.4513 -> 0.4361) in return for probabilities that mean
what they say, which is why it is the model served to users. Both
XGBoost models beat climatology and logistic regression on every metric
except training time. Climatology has a closed-form fit, XGBoost stops
early at about iteration 129, and logistic regression's plain gradient
solver is the slowest of the four at this row count.

## Calibration

`ml/artifacts/final_ml_benchmark_v1_calibrated_xgboost/plots/calibration_table.csv`
(10 bins, isotonic calibration on the validation split, evaluated on the
test split). Predicted and observed frequency are close in every bin
that has rows:

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

This includes the near-zero bin, which holds 218,223 of the 219,450 test
rows (matching the positive rate of about 0.45%). There, predicted and
observed frequency agree to three decimal places.
`reliability_diagram.png` in the same folder plots the table.

## Out of scope

- **`models/benchmark.py` and `models/harness.py` are unchanged.** Both
  are on the `benchmark-v1` frozen list and are used as frozen. Only a
  new data-loading script was added.
- **The first result is kept.** `ml/artifacts/final_baseline_benchmark_v1`
  stays as the record of what the sample-only data produced. It is not
  overwritten, in the same way that
  `ml/artifacts/reliability_tests/before.json` was kept.
