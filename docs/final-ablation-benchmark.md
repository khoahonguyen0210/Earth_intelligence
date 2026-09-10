# Final Ablation Benchmark — LOCKED

This document records Task 16.3, the third task of Phase 16. It is not
a brainstorming document.

Task 16.3 asks for a three-way feature-ablation comparison: fire
history alone, fire history + weather, fire history + weather +
geography. As with Task 16.2, the original ablation demo scripts
(`scripts/models/run_weather_ablation.py` /
`run_geography_ablation.py`, Tasks 5.1/5.2) predate the real historical
dataset and their own docstrings say so -- zero real positive examples
in the sample data's train/validation splits. This task adds
`scripts/models/run_final_ablation_benchmark.py`, which loads the real
dataset (`data/processed/historical_dataset_v1.csv`) and calls the
frozen, unmodified `models/ablation.py::run_weather_ablation` /
`run_geography_ablation` (`benchmark-v1`) -- same protocol as Task
16.2: the comparison logic is untouched, only the data changed.

## Results

`ml/artifacts/final_ablation_benchmark_v1/{weather,geography}_ablation.json`:

```text
Variant                                    PR-AUC    ROC-AUC   Brier     LogLoss
fire_history_only                          0.3559    0.9119    0.0025    0.0173
fire_history_plus_weather                  0.3703    0.9002    0.0024    0.0179
fire_history_plus_weather_plus_geography   0.4513    0.9669    0.0022    0.0101

weather delta   (fire_history -> +weather):        PR-AUC +0.0144  ROC-AUC -0.0117
geography delta (+weather -> +weather+geography):  PR-AUC +0.0811  ROC-AUC +0.0667
```

**Achieved a PR-AUC gain of +0.081 (0.370 -> 0.451) by adding
elevation, slope, and land cover on top of fire history and weather --
more than five times the gain weather features alone provided.**

Weather's own contribution is small and mixed: a modest PR-AUC gain
(+0.0144) alongside a small ROC-AUC *decrease* (-0.0117), on a fire-
history-only baseline that is already strong (ROC-AUC 0.9119) -- wind,
temperature, precipitation, and humidity mostly overlap with what
recent fire counts nearby already signal, at this feature set and this
real data volume. Geography is unambiguous: every metric improves,
consistent with wildfire risk depending heavily on static terrain
(steep, high-elevation, certain land-cover tiles burn differently than
flat agricultural ones) in a way recent fire counts and short-term
weather cannot substitute for.

**Cross-check against Task 16.2.** The third row here
(`fire_history_plus_weather_plus_geography`) uses the exact same
feature columns, model config, and data as Task 16.2's `xgboost` row --
and the two independently-run numbers match exactly (PR-AUC 0.4513,
ROC-AUC 0.9669 in both), the same determinism
`test_production_model.py` (Task 15.4) already proved for the fixed
`random_state`.

## What this task does not do

- **Does not change `models/ablation.py`.** On the `benchmark-v1`
  frozen list, used exactly as frozen; only a new data-loading script
  was added, the same pattern as Task 16.2.
- **Does not re-run `ml/tests/models/test_ablation.py`'s own synthetic,
  separable-data proof** that weather/geography features measurably
  help *when the signal is designed to be there* -- that test's job is
  proving the ablation mechanism itself works, not measuring the real
  effect size, which is what this task does instead.
