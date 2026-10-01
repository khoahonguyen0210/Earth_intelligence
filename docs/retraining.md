# Gated Retraining

When a new fire season of data arrives, the system trains a candidate
model and replaces the model in service only if the candidate is
clearly better. Every candidate is kept, every run is logged, and a
promotion can be rolled back.

```text
new season of data -> train candidate -> score candidate and current model
                    -> clearly better? -- no  -> keep current, log the run
                                       \- yes -> promote, deploy, log the run
```

## Which data each run uses

A run is named by its newest season, `Y`. It uses an expanding window
(`models/retraining.py`, `season_windows`):

| Role | Seasons |
|---|---|
| Fit the candidate | every season before `Y - 1` |
| Early stopping and isotonic calibration | `Y - 1` |
| Gate: score candidate and current model | `Y` |

The gate season is new to both models. The candidate never trained or
calibrated on it, and the current model came from an earlier run with
an older newest season. So the comparison is fair, and it is made on
data neither model has seen, which is how the next season will look in
service.

**2024 is the locked test season and can never be a gate.** The
published benchmark scores the model on 2024, so 2024 must never decide
which model is chosen. Runs gated on 2025 or later may use 2024 as
training data, since the benchmark is already frozen.

## When a candidate is promoted

`decide` promotes a candidate only if, on the gate season:

- its PR-AUC is at least **0.01** higher than the current model's, and
- its Brier score is no more than **5%** worse, so better ranking is not
  bought with worse probabilities.

A smaller gain keeps the current model. Year-to-year noise is large (a
single season gives 95% intervals of several hundredths), and every
swap carries risk of its own. Each run also records a 95% bootstrap
interval for the gain, resampling whole forecast dates as in
`docs/evaluation.md`, so a reviewer can see how certain the gain was.

## The registry

`ModelRegistry` keeps, under `ml/artifacts/model_registry/`:

- `versions/<version>/`: the model, its metadata (including the seasons
  it used), and its feature reference for drift checks, for **every**
  candidate, promoted or not;
- `registry.json`: the version in service, the promotion history, and
  every run with both models' scores, the gain interval and the reason
  for the decision.

Deploying copies the chosen version next to the served directory and
then swaps it in, so the served path always holds one complete model.
A forecast reports the version that produced it, read from the model's
own metadata. `rollback` returns to the version promoted before the
current one.

```bash
python scripts/models/retrain.py --register-current      # adopt the served model as v1
python scripts/models/retrain.py --season 2025 --deploy  # once 2025 is in the dataset
python scripts/models/retrain.py --rollback --deploy
```

## Backtest on past seasons

There is no 2025 data yet, so the loop was replayed on history
(`python scripts/models/retrain.py --replay`) in a separate registry,
leaving the served model untouched. Three runs, gated on 2021, 2022
and 2023:

| Run | Candidate fit on | Gate | Candidate PR-AUC | Current PR-AUC | Gain (95% interval) | Decision |
|---|---|---|---|---|---|---|
| 1 | 2019 | 2021 | 0.597 | none | none | promoted, first model |
| 2 | 2019 to 2020 | 2022 | 0.374 | 0.415 | -0.041 (-0.075 to -0.007) | kept current |
| 3 | 2019 to 2021 | 2023 | 0.450 | 0.445 | +0.006 (-0.009 to +0.019) | kept current |

What this shows:

- **More data did not make a better model.** In run 2 the candidate had
  twice the training seasons and was significantly worse on the next
  season. A loop that always deployed the newest model would have made
  forecasts worse.
- **The gate also held back a gain that was within noise.** Run 3's
  candidate was ahead by 0.006, but its interval included zero.
- The first model, fit on 2019 alone, stayed in service for all three
  replayed seasons.

PR-AUC also swings a lot between seasons for the same kind of model
(0.597 on 2021, 0.415 on 2022). Each season has a different fire
count and pattern, so scores from different gate seasons should not be
compared with each other, only candidate against current on the same
season.

## Limits

- The runs are started by hand. A schedule is easy to add, but building
  a new season's dataset needs the FIRMS and ERA5 download keys, which
  CI does not hold.
- A promoted candidate keeps the training it had at gate time. It is
  not refit to include the gate season.
- Promotion is decided on PR-AUC and Brier score on one season. Spatial
  generalisation (`docs/evaluation.md`) is not part of the gate.
