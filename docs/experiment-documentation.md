# Experiment Documentation — LOCKED

This document records the experiment documentation. It is not
a brainstorming document. Every final experiment below follows the
handbook's own fixed card: purpose, dataset/version, feature version,
split, configuration, command, metrics, result, limitations. Every
number is copied from its own locked source document
(`docs/*-benchmark.md`); nothing here is re-derived.

---

## Production model training

**Purpose.** Train the one calibrated-XGBoost model the product
actually serves (`POST /forecasts`), on the real historical dataset.

**Dataset/version.** `data/processed/historical_dataset_v1.csv`, `v1`.

**Feature version.** `v1` (fire history + weather + geography, the
locked feature set — `docs/scientific-regression-tests.md`).

**Split.** Train 877,800 rows (2019-06-01 → 2022-10-26); validation
219,450 rows (2023-06-01 → 2023-10-26); test split loaded but never
used by this experiment.

**Configuration.** `xgboost_model.BASE_CONFIG`: `n_estimators=500,
max_depth=4, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
random_state=20240815`; isotonic calibration on the validation split.

**Command.**
```bash
python scripts/forecast/build_historical_dataset.py   # once
python scripts/models/train_production_model.py
```

**Metrics.** None computed directly by this script — see "Final ML
benchmark" below for the same configuration's measured metrics.

**Result.** `ml/artifacts/production_model_v1/{model.pkl,metadata.json}`,
loaded by every real forecast request (`docs/end-to-end-test-pass.md`'s
live `SUCCEEDED` run: 9,975 grid cells, real calibration table).

**Limitations.** One fixed configuration, never hyperparameter-tuned
beyond its original documented starting point; refuses to load
on any library-version drift rather than risk silently different
predictions.

---

## Final ML benchmark

**Purpose.** Compare all four locked models (Climatology, Logistic
Regression, XGBoost, Calibrated XGBoost) on real data for the first
time.

**Dataset/version.** `data/processed/historical_dataset_v1.csv`, `v1`.

**Feature version.** `v1`.

**Split.** Train 877,800 / validation 219,450 / test 219,450 rows
(same cutoffs as above; test split now scored).

**Configuration.** Same `BASE_CONFIG` as production training; identical
across every model in the ladder except the model class itself.

**Command.** `python scripts/models/run_ml_benchmark.py`

**Metrics.** PR-AUC, ROC-AUC, Brier score, log loss, training/inference
time.

**Result.**
```text
climatology           PR-AUC 0.2522   ROC-AUC 0.8616   Brier 0.0026   LogLoss 0.0341
logistic_regression   PR-AUC 0.2782   ROC-AUC 0.9463   Brier 0.0649   LogLoss 0.2473
xgboost                PR-AUC 0.4513   ROC-AUC 0.9669   Brier 0.0022   LogLoss 0.0101
calibrated_xgboost      PR-AUC 0.4361   ROC-AUC 0.9667   Brier 0.0022   LogLoss 0.0108
```
Full detail, including the calibration table: `docs/ml-benchmark.md`.

**Limitations.** Logistic regression is the slowest of the four
(70.7s) at this row count with its plain solver; no hyperparameter
search performed for any model — one fixed, documented configuration
per the locked model ladder.

---

## Final ablation benchmark

**Purpose.** Measure the real effect of weather and geography features
on top of fire history alone.

**Dataset/version.** `data/processed/historical_dataset_v1.csv`, `v1`.

**Feature version.** Three variants: fire-history-only (5 columns),
+weather (10 columns), +weather+geography (full `v1`, 12 numeric
columns + land-cover one-hot).

**Split.** Same as the ML benchmark above.

**Configuration.** Same `BASE_CONFIG`; only the feature columns fed to
the model change between variants.

**Command.** `python scripts/models/run_ablation_benchmark.py`

**Metrics.** PR-AUC, ROC-AUC, Brier score, log loss, per variant, plus
PR-AUC/ROC-AUC deltas between adjacent variants.

**Result.**
```text
fire_history_only                          PR-AUC 0.3559   ROC-AUC 0.9119
fire_history_plus_weather                  PR-AUC 0.3703   ROC-AUC 0.9002
fire_history_plus_weather_plus_geography   PR-AUC 0.4513   ROC-AUC 0.9669
```
Full detail: `docs/ablation-benchmark.md`.

**Limitations.** Two-step ablation only (weather, then geography) —
does not measure geography's contribution in isolation without
weather, or any interaction effect between the two groups.

---

## Final distributed scaling benchmark

**Purpose.** Measure real runtime, throughput, speedup, and efficiency
at 1/2/4/8 workers, with workload/data/model held fixed.

**Dataset/version.** The frozen 500-tile workload
(`distributed/workload.py`) against small real sample data
(`data/raw/{firms,era5,geography}/*_sample.*`) — not the full
historical dataset; this experiment measures computational cost, not
model accuracy (`docs/distributed-workload.md`).

**Feature version.** N/A — the model-fitting step falls back to
realistically-shaped synthetic timing rows on this experiment's small
sample data (zero real positive examples), a documented, expected case
(`used_synthetic_model_fallback: true`), since only wall-clock cost is
measured here, not predictive quality.

**Split.** N/A — no train/validation/test split; one fixed workload
processed at each worker count.

**Configuration.** `WORKER_COUNTS = (1, 2, 4, 8)`.

**Command.** `python scripts/distributed/run_scaling_benchmark.py`

**Metrics.** Wall-clock seconds, throughput (tiles/second), speedup
(`T1/Tn`), efficiency (`speedup(n)/n`).

**Result.**
```text
workers   wall_s    throughput   speedup   efficiency
      1    0.851       587.49      1.000       1.000
      2    9.488        52.70      0.090       0.045
      4   12.109        41.29      0.070       0.018
      8   22.381        22.34      0.038       0.005
```
Full detail: `docs/distributed-benchmark.md`.

**Limitations.** Monotonically slower with more workers on this
project's Windows/`multiprocessing.spawn` platform — process-spawn
overhead dominates this workload's genuinely small real compute
(`docs/bottleneck-identification.md`'s own finding); not evidence
against parallelism in general, only against this platform/workload-size
combination.

---

## Final fault-injection (failure/recovery) test

**Purpose.** Measure real detection and recovery when one worker is
genuinely killed mid-chunk.

**Dataset/version.** Same frozen 500-tile workload as the scaling
benchmark above.

**Feature version.** N/A, same reasoning as above.

**Split.** N/A.

**Configuration.** `NUM_WORKERS=4, TASK_TIMEOUT_SECONDS=30,
MAX_RETRIES=2, CRASH_CHUNK_INDEX=0` (`os._exit(1)`, observably
identical to an external kill).

**Command.** `python scripts/distributed/run_fault_injection_test.py`

**Metrics.** Failure detected (bool), all chunks eventually succeeded
(bool), tiles recovered / total, total recovery seconds.

**Result.**
```text
any_failure_detected:            true
all_chunks_eventually_succeeded: true
total_tiles_recovered:           500 / 500
total_recovery_seconds:          1.353
```
Full detail: `docs/distributed-benchmark.md`.

**Limitations.** One crash scenario (a single killed worker, one
chunk) — does not cover multiple simultaneous crashes or a crash during
the retry attempt itself; recovery time varies run to run with the
replacement worker's own cold-start cost, not a fixed constant.

---

## Final AI planner benchmark

**Purpose.** Measure the real natural-language planner end to end
against the live LLM API: intent, region, and time correctness, valid-
plan rate, and execution success.

**Dataset/version.** 14 fixed natural-language questions, 2 per
handbook category (`planner/benchmark_set.py::BENCHMARK_CASES`) — not
an ML dataset; the fixed evaluation set for this experiment.

**Feature version.** N/A.

**Split.** N/A — every case is both "training" and "test" in the sense
that the model is not fine-tuned on any of them; this measures the
planner's real, live behavior only.

**Configuration.** `planner.generate_plan.MODEL` (`gemini-3.1-flash-lite`);
one real `generate_plan(question, client)` call per case.

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
Full detail, including run-to-run comparison: `docs/planner-accuracy-benchmark.md`.

**Limitations.** The LLM call is real and unseeded — re-running this
exact experiment does not guarantee the same exact numbers (this run's
`time_correctness` differs from the original 1.0, a genuine
date-range-convention variance, not a code regression); one known,
reproduced miss (a causal "why" question answered instead of rejected).
