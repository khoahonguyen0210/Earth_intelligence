# Wildfire Forecasting Specification — LOCKED

This document freezes the forecasting specification. It is not a
brainstorming document. Do not alter these
values for the main benchmark; a change here invalidates every experiment
built on top of it.

This is a restatement, not a redefinition, of the scientific problem locked
for this project.

## Study region

California, using the same fixed bounding box used throughout the pipeline
from the very beginning (FIRMS, ERA5-Land, geography, grid):

```
west  = -124.5
south =  32.5
east  = -114.0
north =  42.0
```

## Spatial grid

`0.1° x 0.1°`, the California grid already built
(`ai_earth_intelligence_and_forecasting_engine.data.grid`). 9,975 cells.

## Forecast cutoff

Hourly. A cutoff `T` is any hour boundary; a forecast can be produced for
every grid cell at every hourly cutoff.

## Forecast window

Fixed to exactly the next 24 hours after the cutoff. This project does not
produce longer- or shorter-range forecasts as part of the main benchmark.

## Target definition

For grid cell `G` at cutoff `T`:

```
target = 1  if at least one qualifying FIRMS active-fire observation
             occurs in G during (T, T + 24h]

target = 0  otherwise
```

This is a binary occurrence target, not burned area, fire size, or
severity. The exact qualifying-observation filter (which FIRMS
confidence/quality values count) is defined elsewhere and recorded in
code, not restated here, so this document does not drift out of sync with
the implementation.

## Feature availability rule

A feature used to predict cutoff `T` may only use information with
availability time `<= T`. No feature may look forward past its cutoff.
The leakage tests enforce this mechanically; this document states
the rule the tests are built to catch violations of.

## Historical split

```
TRAIN       2019-01-01 -> 2022-12-31
VALIDATION  2023-01-01 -> 2023-12-31
TEST        2024-01-01 -> 2024-12-31
```

The test period is not touched until model configuration is frozen.
Validation data may be used for tuning; test data may not.

## What this document does not define

The exact feature list (fire-history windows, weather variables, static
geography), the model ladder, and the evaluation metrics are already
locked and implemented elsewhere. This document exists so the label
construction and leakage tests have one unambiguous specification to
build against and be tested against, not to duplicate the full research
dossier.
