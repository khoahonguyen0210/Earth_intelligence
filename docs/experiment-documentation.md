# Experiment Documentation

Each final experiment below uses the same card: purpose, dataset and
version, feature version, split, configuration, command, metrics,
result and limitations. Every number is copied from the document that
reports it (`docs/*-benchmark.md`). Nothing here is computed again.

---

## Production model training

**Purpose.** Train the calibrated XGBoost model that the product serves
(`POST /forecasts`) on the historical dataset.

**Dataset and version.** `data/processed/historical_dataset_v1.csv`, `v1`.

**Feature version.** `v1`: fire history, weather and geography, the
fixed feature set (`docs/scientific-regression-tests.md`).

**Split.** Train 877,800 rows (2019-06-01 to 2022-10-26); validation
219,450 rows (2023-06-01 to 2023-10-26). The test split is loaded but
never used here.

**Configuration.** `xgboost_model.BASE_CONFIG`: `n_estimators=500,
max_depth=4, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
random_state=20240815`; isotonic calibration on the validation split.

**Command.**
```bash
python scripts/forecast/build_historical_dataset.py   # once
python scripts/models/train_production_model.py
```

**Metrics.** This script computes none. The "Final ML benchmark" below
reports metrics for the same configuration.

**Result.** `ml/artifacts/production_model_v1/{model.pkl,metadata.json}`.
Every forecast request loads it. The live `SUCCEEDED` run in
`docs/end-to-end-test-pass.md` returned 9,975 grid cells and a
calibration table.

**Limitations.** One fixed configuration with no hyperparameter tuning
beyond its documented starting point. The model refuses to load if a
library version has changed, instead of risking different predictions
without notice.

---

## Final ML benchmark

**Purpose.** Compare the four models (climatology, logistic regression,
XGBoost and calibrated XGBoost) on the full dataset for the first time.

**Dataset and version.** `data/processed/historical_dataset_v1.csv`, `v1`.

**Feature version.** `v1`.

**Split.** Train 877,800, validation 219,450 and test 219,450 rows,
with the same cutoffs as above. The test split is scored here.

**Configuration.** The same `BASE_CONFIG` as production training. Only
the model class differs between models.

**Command.** `python scripts/models/run_ml_benchmark.py`

**Metrics.** PR-AUC, ROC-AUC, Brier score, log loss, training and
inference time.

**Result.**
```text
climatology           PR-AUC 0.2522   ROC-AUC 0.8616   Brier 0.0026   LogLoss 0.0341
logistic_regression   PR-AUC 0.2782   ROC-AUC 0.9463   Brier 0.0649   LogLoss 0.2473
xgboost                PR-AUC 0.4513   ROC-AUC 0.9669   Brier 0.0022   LogLoss 0.0101
calibrated_xgboost      PR-AUC 0.4361   ROC-AUC 0.9667   Brier 0.0022   LogLoss 0.0108
```
Full detail, including the calibration table: `docs/ml-benchmark.md`.

**Limitations.** Logistic regression is the slowest of the four (70.7 s)
at this row count with its plain solver. No model has a hyperparameter
search; each uses one fixed, documented configuration.

---

## Final ablation benchmark

**Purpose.** Measure how much weather and geography features add to fire
history alone.

**Dataset and version.** `data/processed/historical_dataset_v1.csv`, `v1`.

**Feature version.** Three variants: fire history only (5 columns),
plus weather (10 columns), and plus weather and geography (full `v1`,
12 numeric columns and land-cover one-hot).

**Split.** Same as the ML benchmark above.

**Configuration.** The same `BASE_CONFIG`. Only the feature columns
change between variants.

**Command.** `python scripts/models/run_ablation_benchmark.py`

**Metrics.** PR-AUC, ROC-AUC, Brier score and log loss per variant, and
the PR-AUC and ROC-AUC differences between neighboring variants.

**Result.**
```text
fire_history_only                          PR-AUC 0.3559   ROC-AUC 0.9119
fire_history_plus_weather                  PR-AUC 0.3703   ROC-AUC 0.9002
fire_history_plus_weather_plus_geography   PR-AUC 0.4513   ROC-AUC 0.9669
```
Full detail: `docs/ablation-benchmark.md`.

**Limitations.** The ablation has two steps only (weather, then
geography). It does not measure geography without weather, or how the
two groups interact.

---

## Final distributed scaling benchmark

**Purpose.** Measure runtime, throughput, speedup and efficiency at 1,
2, 4 and 8 workers, with the workload, data and model held fixed.

**Dataset and version.** The frozen 500-tile workload
(`distributed/workload.py`) on small sample data
(`data/raw/{firms,era5,geography}/*_sample.*`), not the full historical
dataset. This experiment measures compute cost, not model accuracy
(`docs/distributed-workload.md`).

**Feature version.** Not applicable. The sample data has no positive
examples, so the model-fitting step falls back to synthetic timing rows
with a realistic shape (`used_synthetic_model_fallback: true`). This is
expected and documented, because only time is measured here, not
prediction quality.

**Split.** Not applicable. One fixed workload is processed at each
worker count.

**Configuration.** `WORKER_COUNTS = (1, 2, 4, 8)`.

**Command.** `python scripts/distributed/run_scaling_benchmark.py`

**Metrics.** Wall-clock seconds, throughput (tiles per second), speedup
(`T1/Tn`) and efficiency (`speedup(n)/n`).

**Result.**
```text
workers   wall_s    throughput   speedup   efficiency
      1    0.851       587.49      1.000       1.000
      2    9.488        52.70      0.090       0.045
      4   12.109        41.29      0.070       0.018
      8   22.381        22.34      0.038       0.005
```
Full detail: `docs/distributed-benchmark.md`.

**Limitations.** On this Windows setup with `multiprocessing.spawn`,
each added worker makes the run slower. The cost of starting processes
outweighs the small amount of compute
(`docs/bottleneck-identification.md`). This says nothing against
parallel work in general, only about this platform and workload size.

---

## Final fault-injection (failure and recovery) test

**Purpose.** Measure detection and recovery when one worker is killed
during its chunk.

**Dataset and version.** The same frozen 500-tile workload as the
scaling benchmark above.

**Feature version.** Not applicable, for the same reason as above.

**Split.** Not applicable.

**Configuration.** `NUM_WORKERS=4, TASK_TIMEOUT_SECONDS=30,
MAX_RETRIES=2, CRASH_CHUNK_INDEX=0` (`os._exit(1)`, which looks the same
to the parent process as a kill from outside).

**Command.** `python scripts/distributed/run_fault_injection_test.py`

**Metrics.** Failure detected (true or false), all chunks finally
succeeded (true or false), tiles recovered out of the total, and total
recovery seconds.

**Result.**
```text
any_failure_detected:            true
all_chunks_eventually_succeeded: true
total_tiles_recovered:           500 / 500
total_recovery_seconds:          1.353
```
Full detail: `docs/distributed-benchmark.md`.

**Limitations.** One crash case only: one killed worker on one chunk.
It does not cover several crashes at once or a crash during the retry.
Recovery time changes from run to run with the start-up cost of the
replacement worker.

---

## Final AI planner benchmark

**Purpose.** Measure the planner end to end against the live LLM API:
intent, region and time correctness, valid-plan rate and execution
success.

**Dataset and version.** 14 fixed questions, 2 per category
(`planner/benchmark_set.py::BENCHMARK_CASES`). This is a fixed
evaluation set, not an ML dataset.

**Feature version.** Not applicable.

**Split.** Not applicable. The model is not fine-tuned on any case, so
this measures only how the planner behaves live.

**Configuration.** `planner.generate_plan.MODEL` (`gemini-3.1-flash-lite`);
one `generate_plan(question, client)` call per case.

**Command.** `python scripts/query/run_planner_benchmark.py` (needs
`GEMINI_API_KEY` in `.env`)

**Metrics.** `intent_correctness`, `region_correctness`,
`time_correctness`, `valid_plan_rate`, `execution_success`,
`unsupported_request_handling`.

**Result.**
```text
intent_correctness:          1.0   (12/12 scored)
region_correctness:          1.0   (12/12 scored)
time_correctness:            0.667 (8/12 scored)
valid_plan_rate:             0.917 (11/12 scored)
execution_success:           1.0   (14/14)
unsupported_request_handling: 0.5   (1/2)
```
Full detail, including the comparison between runs:
`docs/planner-accuracy-benchmark.md`. The later 22-question version is
in `docs/evaluation.md`.

**Limitations.** The LLM call is live and has no fixed seed, so a rerun
may not give the same numbers. In this run, `time_correctness` differs
from the first run's 1.0 because the model chose a different date-range
convention, not because of a code change. One known miss repeats: a
"why" question is answered instead of rejected.
