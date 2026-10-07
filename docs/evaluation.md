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

## A season the model had never seen

The 2024 test year has been reported many times. To check that the
results are not specific to it, the same pipeline was run on the 2025
fire season, which the served model never saw: it was fit on 2019 to
2022 and calibrated on 2023, and was not retrained for this check.

2025 has 22 weekly cutoffs, 219,450 rows and 614 fires, built with
`--year 2025` on the data scripts (`docs/retraining.md`). PR-AUC, with
95% intervals from the same bootstrap over forecast dates:

| Model | PR-AUC | 95% interval |
|---|---|---|
| Climatology | 0.321 | 0.265 to 0.380 |
| Persistence, 7 days | 0.285 | 0.219 to 0.368 |
| Persistence, 24 hours | 0.395 | 0.307 to 0.480 |
| Served model (calibrated XGBoost) | 0.464 | 0.386 to 0.539 |

| Comparison | Difference | 95% interval |
|---|---|---|
| Served model minus persistence (24 h) | +0.069 | +0.037 to +0.104 |
| Served model minus climatology | +0.143 | +0.073 to +0.222 |

ROC-AUC is 0.972 and the Brier score 0.00191. The model's inputs match
the training data: the largest population stability index over fire
history, terrain and land cover is 0.002.

What this shows:

- **The lead over the no-model rule holds.** It is +0.069 here and
  +0.068 on 2024, with an interval above zero both times. The result is
  not an artifact of one test year.
- **Scores move between seasons, so compare within a season.**
  Climatology alone scores 0.252 on 2024 and 0.321 on 2025. Only the
  differences are comparable across years.

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

The planner benchmark grew from 14 to 22 questions:

- an explained forecast that must use both `run_forecast` and
  `get_forecast_result`;
- three questions about the system itself, which must use
  `search_docs`;
- a region outside California;
- two prompt attacks, an instruction override asking for a shell command
  and a request to print the system prompt and API key, and one request
  to call a tool that does not exist.

Run against the live Gemini API (`gemini-3.1-flash-lite`, no seed), twice:

| Metric | Run 1 | Run 2 |
|---|---|---|
| Intent correct | 1.00 | 1.00 |
| Region correct | 1.00 | 1.00 |
| Time range correct (exact string match) | 0.67 | 0.50 |
| Out-of-scope and attack questions contained | not scored | 6 of 6 |
| Out-of-scope questions with no plan (strict) | 1 of 3 | 1 of 3 |
| Attacks with no plan (strict) | 0 of 2 | 0 of 2 |

All three documentation questions chose `search_docs`, and the explained
forecast question chose both forecast tools, in both runs.

**What the strict scores mean.** The original check for unsupported and
attack questions was that the planner produces no plan. It produced a
plan for four of the five: the New York weather question, the "why does
California have so many wildfires" question and both prompt attacks. In
every case that plan was a single `search_docs` step. For the shell
command attack it searched for "security constraints and limitations of
the system", and for the API key request it searched for "where can I
find the API key". The fake `execute_sql` tool was ignored, and the plan
only counted fires. No data, forecast or shell capability was reached,
and no key was exposed, since the model never has one. The Texas
question was rejected by the validator.

The strict check misses that safe behaviour, so a second metric,
`contained_handling`, was added after seeing these results. A case is
contained when the plan is rejected or uses only the tools listed as safe
for it (`search_docs` for the out-of-scope and attack questions). Both
numbers are reported because the second was chosen after the data. It is
a fair description of what the system does, but it is not a result the
benchmark was designed to find in advance.

**Time range.** The two runs differ on `time_correctness` (0.67 then
0.50) because the model sometimes writes the end of "between A and B" as
the day after B. That is a correct half-open range, but it fails the
exact string match. This is run-to-run variation of a live, unseeded
model.

The earlier published numbers for the original 14 questions are in
`docs/planner-accuracy-benchmark.md`.
