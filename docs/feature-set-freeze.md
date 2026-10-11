# Final Feature Set — LOCKED

This document freezes the feature set for the main benchmark. It is not a
brainstorming document. Do not alter
this decision after looking at test-set numbers; a change here invalidates
the honesty of every ablation and benchmark result built on top of it.

## The frozen decision

The main benchmark uses the **complete** locked feature set already defined
for this project — fire-history, weather, and
static geography (including land-cover category) together. Nothing is
dropped.

In code, this is exactly the default behavior of `fit_preprocessor`,
`fit_xgboost`, and `evaluate_xgboost`
(`ml/src/ai_earth_intelligence_and_forecasting_engine/models/`): calling
them with no `feature_columns`/`include_land_cover` override uses
`NUMERIC_FEATURE_COLUMNS` (fire-history + weather + elevation + slope) plus
the land-cover one-hot. The existing `run_baseline_benchmark` and every
script under `scripts/models/` that does not explicitly restrict features
(everything except the two ablation demos) already benchmark against this
full set. No code change was needed to freeze this — the task is the
decision not to shrink it.

## Why this isn't a cherry-pick

The weather ablation and the geography ablation exist to
*measure* whether each feature group helps, using
`ml/src/ai_earth_intelligence_and_forecasting_engine/models/ablation.py`.
As of this freeze, neither ablation has a real measured result: the
project has only ingested real historical FIRMS data for one real day, so
the real train/validation splits have zero real positive examples and
every XGBoost-based variant (baseline and candidate alike, in both
ablations) fails the same honest single-class check documented in
`ml/tests/models/test_xgboost_model.py`. See
`ml/artifacts/weather_ablation_v1/weather_ablation.json` and
`ml/artifacts/geography_ablation_v1/geography_ablation.json` for the
actual (null-delta) real runs, and `ml/tests/models/test_ablation.py` for
proof the ablation code correctly measures a feature group's contribution
once separable data is available.

Because there is no real per-group signal to react to yet, freezing the
full locked set is not a data-driven choice among several observed
variants — it is simply using the feature set
already specified, unchanged. This is deliberate: once real historical
data is ingested and the ablations produce real deltas, this frozen
decision is still not to be revisited by picking whichever subset scored
best on that day's numbers. A future change to the main benchmark's
feature set must be its own pre-registered decision (a new locked
document, reasoned about before looking at test-set results), not a
post-hoc reaction to one experiment.

## What this document does not define

The exact feature list, model ladder, and metrics are already locked
elsewhere in the project. This document exists only to
record the freeze decision and the reasoning behind it, not to
restate or redefine the feature list itself.
