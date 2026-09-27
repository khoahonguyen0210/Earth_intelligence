# Evaluation

The original benchmark reports one PR-AUC per model on the 2024 test
year. This document adds what a single number cannot show: how
uncertain it is, whether the model beats a trivial rule, how it does in
places it never trained on, and whether its inputs drift.

Nothing here tunes the model on the test set. The locked config is
reused as is, and the four benchmarked models' saved test predictions
are re-scored.

Reproduce with:

```bash
python scripts/models/run_rigorous_evaluation.py
python scripts/models/build_feature_reference.py
```

## Confidence intervals

PR-AUC on the 2024 test year (219,450 rows, 686 fires, 22 weekly
cutoffs), with 95% intervals from 1,000 bootstrap samples.

The bootstrap resamples **whole forecast cutoffs**, not rows. All cells
of one cutoff share that day's weather and fire season, so resampling
rows would treat correlated rows as independent and give intervals far
too narrow.

| Model | PR-AUC | 95% interval |
|---|---|---|
| Climatology | 0.252 | 0.175 to 0.333 |
| Logistic regression | 0.278 | 0.216 to 0.346 |
| Persistence, 7 days | 0.278 | 0.212 to 0.346 |
| Persistence, 24 hours | 0.384 | 0.315 to 0.447 |
| Calibrated XGBoost (served) | 0.436 | 0.360 to 0.503 |
| XGBoost | 0.451 | 0.374 to 0.521 |

The served model is the calibrated one. Isotonic calibration makes its
probabilities match observed frequencies, and costs 0.015 PR-AUC
against uncalibrated XGBoost.

## A trivial baseline is the real bar

**Persistence** uses no model: a cell's risk score is its fire count in
the last 24 hours (or 7 days), with ties broken by the 30-day count. It
is the rule "fire continues where it just burned".

Paired differences, same bootstrap:

| Comparison | Difference | 95% interval |
|---|---|---|
| XGBoost minus climatology | +0.199 | +0.125 to +0.265 |
| XGBoost minus persistence (24 h) | +0.068 | +0.031 to +0.101 |
| Calibrated XGBoost minus persistence (24 h) | +0.052 | +0.017 to +0.086 |
| Logistic regression minus climatology | +0.026 | -0.055 to +0.097 |
| Logistic regression minus persistence (24 h) | -0.106 | -0.136 to -0.079 |

What this shows:

- XGBoost's lead over climatology is large and clearly real.
- Against "fires yesterday", the lead is much smaller: about +0.07
  PR-AUC. It is still above zero across the whole interval, so the model
  adds real value, but most of what a simple rule already knows is
  recent fire.
- Logistic regression is not distinguishable from climatology and is
  worse than persistence.

## Places the model never saw

The grid is split into 1-degree blocks (10 x 10 cells), assigned to 5
folds so that no two adjacent blocks share a fold. For each fold,
XGBoost is retrained without that fold's blocks, using the same locked
config, and scored on those blocks in the 2024 test year. Every test
row thus gets a prediction from a model that never trained on its
region.

| | PR-AUC | 95% interval |
|---|---|---|
| Blocks seen in training | 0.451 | 0.374 to 0.521 |
| Blocks hidden from training | 0.346 | 0.284 to 0.413 |
| Hidden minus seen | -0.105 | -0.138 to -0.077 |

| Fold | Test fires | Seen | Hidden |
|---|---|---|---|
| 0 | 69 | 0.332 | 0.212 |
| 1 | 136 | 0.565 | 0.527 |
| 2 | 170 | 0.430 | 0.325 |
| 3 | 156 | 0.514 | 0.474 |
| 4 | 155 | 0.374 | 0.318 |

The model is partly learning where fires happen, not only why. In an
area it never trained on, PR-AUC falls by about a quarter, below the
0.384 of the persistence rule. The served model is trained on all
of California, so this matters for any use outside California, not for
the product as it runs today.

## Input drift

`scripts/models/build_feature_reference.py` stores the training
distribution of every input (decile bins, plus a missing bin, and land
cover class shares) next to the served model as
`feature_reference.json`, then measures the population stability index
(PSI). Under 0.1 is stable, 0.1 to 0.25 a moderate shift, over 0.25 a
major one.

**By year:**

- The 2024 test year matches the training years. Its largest PSI is
  0.090, on precipitation.
- 2023 shows moderate shifts in precipitation (0.198) and humidity
  (0.135). PSI measures how far a distribution moved, not in which
  direction.

**Per forecast:** one forecast holds a single day of weather for every
cell, and the reference pools 88 training days. Measured on each of the
22 test cutoffs:

| Inputs checked per forecast | Cutoffs flagged major | Largest PSI, median / max |
|---|---|---|
| Weather | 22 of 22 | 1.25 / 6.22 |
| Fire history, terrain, land cover | 0 of 22 | 0.004 / 0.141 |
| Same, with the fire feed simulated as down (all counts 0) | 0 of 22 | 0.187 / 0.187 |

So a per-forecast weather check would raise an alarm on every forecast,
and is not useful. Each forecast therefore checks fire history,
terrain and land cover only, and returns the result in its evidence as
`inputs.drift`. Weather drift is checked over a whole season with the
script.

The honest limit: a dead fire feed raises the per-forecast PSI only to
0.187, a moderate shift, close to the 0.141 seen on one normal cutoff.
Most training rows already have zero fire counts, so an all-zero
forecast does not look very different. PSI alone is a weak detector of
that failure.

## Planner benchmark

The planner benchmark grew from 14 to 19 questions:

- an explained forecast that must use both `run_forecast` and
  `get_forecast_result`;
- a region outside California, which must be rejected;
- three adversarial prompts: an instruction override asking for a shell
  command, a request to print the system prompt and API key, and a
  request to call a tool that does not exist.

A new metric, `adversarial_rejection`, scores the attacks that must
produce no plan. The invented-tool case is recorded but not scored. A
plan that ignores the fake tool and only counts fires is a safe
outcome, and the validator rejects any tool outside the allowlist
regardless.

These new questions have not been run against the live Gemini API yet,
so the published planner numbers (`docs/planner-accuracy-benchmark.md`)
still cover the original 14.
