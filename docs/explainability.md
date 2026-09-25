# Explainability

Every forecast now says why it came out the way it did. The served
model is calibrated XGBoost, and each prediction is broken down into
the contribution of each input with SHAP.

## How it is computed

`models/explain.py` asks XGBoost for exact tree SHAP values
(`pred_contribs=True`) on the base model, using the same trees the
prediction used (its early-stopping `best_iteration`).

- **Units are log-odds**, not probability. The contributions explain
  the raw XGBoost score. Isotonic calibration then maps that score to
  the probability users see, and calibration is monotonic, so a feature
  that raises the score also raises the probability. The size of the
  effect in probability terms is not the same number.
- **Contributions add up.** For every row, the contributions plus the
  expected log-odds equal the model's own score. `tests/models/test_explain.py`
  checks this against XGBoost's raw margin and against `predict_proba`.
- **Land cover is one feature.** Its 11 one-hot columns are summed, so
  "land cover" appears once instead of as 11 separate classes.

## What a forecast returns

- Each grid cell carries its `top_drivers`: the three inputs that moved
  its score most, with sign (positive raises risk).
- The result carries `explanation.importance`: the mean absolute
  contribution of each input over the requested region.
- The planner tool `get_forecast_result` passes these to the answer
  generator, so an answer can say what drove a forecast and the number
  check in `docs/grounded-answer-generation.md` can verify it.
- The forecast page lists the main drivers and names the top drivers of
  the riskiest cell. Hovering a cell shows its own drivers.

## What it costs

Measured on one statewide forecast (all 9,975 California cells, cutoff
2024-08-15 10:00 UTC) with the real model and data:

| | Without SHAP | With SHAP |
|---|---|---|
| Explanation time | none | 1.79 s of a 9.04 s forecast |
| Result size | 4.04 MB | 5.91 MB (+46%) |

Statewide is the worst case. A named sub-region or a bounding box has
far fewer cells, so both costs shrink with it.

## What drives the model on the 2024 test year

Measured with `scripts/models/explain_production_model.py` on the
served model (`v1`) over all 219,450 held-out 2024 test rows, 686 of
which had a fire. The model was not refit or tuned for this; it only
reads the trained artifact. Expected log-odds is -6.27.

| Input | All test rows | Rows with a fire |
|---|---|---|
| Fires in the past 30 days | 0.913 | 1.189 |
| Elevation | 0.596 | 0.270 |
| Slope | 0.300 | 0.108 |
| Fires in the past 7 days | 0.261 | 4.226 |
| Fires in neighboring cells, past 24 h | 0.234 | 0.291 |
| Fires in the past 24 hours | 0.232 | 0.481 |
| Land cover | 0.207 | 0.207 |
| Fires in the past 3 days | 0.174 | 1.041 |
| Relative humidity | 0.150 | 0.078 |
| East-west wind | 0.134 | 0.084 |
| Air temperature | 0.087 | 0.093 |
| North-south wind | 0.076 | 0.054 |
| Precipitation | 0.054 | 0.083 |

Mean absolute SHAP contribution, log-odds.

What this shows:

- **Recent fire history decides the fire rows.** Where a fire really
  happened, fires in the past 7 days contribute 4.23 on average, more
  than every other input combined.
- **Terrain sets the baseline everywhere else.** Over all rows, most of
  which never burn, elevation and slope rank second and third. This
  agrees with the ablation result that terrain and land cover add
  +0.081 PR-AUC (`docs/ablation-benchmark.md`).
- **Weather contributes least.** The five weather inputs are the bottom
  five on all rows, matching the ablation's small and mixed weather
  effect.

These are explanations of what the model learned, not causes of fire.
A feature with a large contribution is one the model relies on, which
can include patterns that are only correlated with fire.
