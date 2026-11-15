# Final Feature Set

This document fixes the feature set for the main benchmark. The
decision must not change after looking at test-set numbers, because
that would make every ablation and benchmark built on it unreliable.

## Decision

The main benchmark uses the **complete** feature set defined for the
project: fire history, weather and static geography (including the
land-cover category) together. Nothing is dropped.

In code, this is the default behavior of `fit_preprocessor`,
`fit_xgboost` and `evaluate_xgboost`
(`ml/src/ai_earth_intelligence_and_forecasting_engine/models/`). Called
without a `feature_columns` or `include_land_cover` override, they use
`NUMERIC_FEATURE_COLUMNS` (fire history, weather, elevation and slope)
plus the land-cover one-hot columns. `run_baseline_benchmark` and every
script under `scripts/models/` that does not restrict features (all
except the two ablation demos) already use this full set. No code
change was needed. The decision is simply not to shrink the set.

## Why this is not a selection made after the fact

The weather and geography ablations measure whether each feature group
helps, using
`ml/src/ai_earth_intelligence_and_forecasting_engine/models/ablation.py`.
When this decision was made, neither ablation had a result. Only one
day of historical FIRMS data had been loaded, so the train and
validation splits had no positive examples. Every XGBoost variant, in
both ablations, failed the single-class check documented in
`ml/tests/models/test_xgboost_model.py`. The runs with no difference are
in `ml/artifacts/weather_ablation_v1/weather_ablation.json` and
`ml/artifacts/geography_ablation_v1/geography_ablation.json`, and
`ml/tests/models/test_ablation.py` shows that the ablation code measures
a feature group's effect correctly once the data has both classes.

With no per-group result to react to, keeping the full set was not a
choice among measured options. It was the feature set already
specified. The rule still holds now that the full data is loaded and
the ablations have results (`docs/ablation-benchmark.md`): the main
benchmark does not switch to whichever subset scored best. Any future
change to its feature set must be decided and written down before
looking at test-set results.

## Out of scope

The feature list, the models and the metrics are defined elsewhere in
the project. This document records only the decision to keep the full
set and the reasons for it.
