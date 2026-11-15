# Final Ablation Benchmark

This benchmark compares three feature sets: fire history alone, fire
history with weather, and fire history with weather and geography. The
first ablation scripts (`scripts/models/run_weather_ablation.py` and
`run_geography_ablation.py`) were written before the historical dataset
existed, and their docstrings say that the sample data has no positive
examples in its train and validation splits.
`scripts/models/run_ablation_benchmark.py` loads the full dataset
(`data/processed/historical_dataset_v1.csv`) and calls the frozen,
unchanged `models/ablation.py::run_weather_ablation` and
`run_geography_ablation` (`benchmark-v1`). The comparison logic is the
same; only the data is new.

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

**Adding elevation, slope and land cover on top of fire history and
weather raised PR-AUC by +0.081 (0.370 -> 0.451).** This is more than
five times the gain from weather features alone.

Weather's effect is small and mixed: PR-AUC rises a little (+0.0144),
while ROC-AUC falls a little (-0.0117). The fire-history baseline is
already strong (ROC-AUC 0.9119). With this feature set and this amount
of data, wind, temperature, precipitation and humidity mostly repeat
what recent nearby fire counts already show. Geography is clear: every
metric improves. Wildfire risk depends strongly on fixed terrain. Steep,
high or certain land-cover tiles burn differently from flat farmland,
and recent fire counts and short-term weather cannot stand in for that.

**Cross-check with the final ML benchmark.** The third row
(`fire_history_plus_weather_plus_geography`) uses the same feature
columns, model settings and data as the `xgboost` row of the final ML
benchmark. The two separate runs give the same numbers (PR-AUC 0.4513
and ROC-AUC 0.9669 in both). `test_production_model.py` already shows
that the fixed `random_state` makes training deterministic.

## Out of scope

- **`models/ablation.py` is unchanged.** It is on the `benchmark-v1`
  frozen list and is used as frozen. Only a new data-loading script was
  added, as for the final ML benchmark.
- **`ml/tests/models/test_ablation.py` is not repeated here.** That test
  uses synthetic data in which weather and geography are built to help,
  to prove that the ablation code works. This benchmark measures the
  size of the effect on the full data.
