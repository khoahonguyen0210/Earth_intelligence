# Multi-Day Wildfire Risk (E7)

The main forecast covers the next 24 hours and uses only weather that
was already observed. This experiment asks whether forecast weather from
an NVIDIA Earth-2 model makes wildfire risk useful for 1, 2 and 3 days
ahead.

Research questions:

- **RQ7.** Does forecast weather add value beyond fire history and
  geography for day +1 to +3?
- **RQ8.** How fast does skill fall with lead time, compared with
  persistence and climatology?

This specification was fixed before any E7 forecast was run. It does not
change the main benchmark, its splits or its results.

## Specification

| Item | Choice |
|---|---|
| Lead days | +1, +2, +3. Day *d* is the 24 hours from cutoff + (*d* − 1) days to cutoff + *d* days. Day +1 is the main benchmark's target. |
| Target | A FIRMS fire in the 0.1° cell during that day, with the same filter as the main target |
| Cutoffs | The main dataset's cutoffs: 10:00 UTC, every 7 days from June 1 to late October, 22 per year |
| Years | 2019 to 2023 and 2025. The 2024 held-out test year is not used. |
| Split | Train 2019 to 2022, validation 2023, test 2025 season |
| Weather model | SFNO from Earth2Studio, default package. As released, it runs out of memory on a T4 ([T4 table](earth2-models-on-t4.md)), so its per-pixel layers run in blocks of 64 latitude rows. The model and its weights do not change. |
| Initial conditions | ERA5 from ARCO at 06:00 UTC on the cutoff day, the latest 6-hour time at or before the cutoff |
| Forecast steps | 11 steps of 6 hours, to 00:00 UTC three days later |
| Features | Fire history (5 counts), elevation, slope, land cover, and four forecast values for the lead day |
| Forecast values | The day's highest index, highest wind, highest vapor pressure deficit (VPD) and highest 2 m temperature, from the 12, 18 and 00 UTC forecasts in that day, interpolated from the 0.25° model grid to each cell's center |
| Model | XGBoost with the fixed settings, early stopping on validation, isotonic calibration on validation. No tuning. |
| Baselines | Climatology, persistence (previous 24-hour count), the production 24-hour model used unchanged for every lead, and XGBoost without forecast values |
| Metrics | PR-AUC, ROC-AUC, Brier score and log loss per lead day |
| Intervals | 95% block bootstrap over forecast dates, 1,000 samples, fixed seed, as in `docs/evaluation.md` |

**Decision rule for RQ7.** Forecast weather adds value for a lead day
only if the 95% interval of the PR-AUC difference (with forecast values
minus without) is entirely above zero.

## Index version

SFNO outputs 2 m temperature, 10 m wind, surface pressure and
temperature, humidity and wind on pressure levels, but no 2 m dew point.
So the index is the **HDWI approximation** (`hdwi_approx_v1`):

- The surface VPD uses 2 m temperature and the humidity of the lowest
  pressure level above the ground, taken at surface pressure.
- Levels are 1000, 925, 850, 700, 600 and 500 hPa. With this spacing, the
  paper's layer (every level up to the first one more than 50 hPa above
  the surface) is often deeper than 500 m.

A model with a 2 m dew point would use the paper's surface term
directly (`hdwi_v1`).

## Leakage rules

- Every forecast starts at or before its cutoff. A test checks this for
  every cutoff, and loading stops if a stored forecast starts later.
- Values valid after the cutoff are used only as forecasts. Reanalysis
  after the cutoff is never a feature.
- Fire history and geography come from the main dataset, whose
  leakage tests already pass.
- Day +1 labels are rebuilt from FIRMS and checked against the main
  target. Any difference is reported.
- Early stopping and calibration use the validation year only. The test
  season is scored once.

Backtests start from reanalysis. A live forecast would start from an
operational analysis, which is less accurate. Results here are therefore
likely an upper bound for live use.

## Cost

132 forecasts of 11 steps each. The estimate is about 5 GPU-hours,
mostly for downloading initial conditions, and the cap is 15 GPU-hours.
Kaggle gives about 30 free GPU-hours per week, and one run may last
up to 12 hours. The notebook first runs one cutoff as a short check. If
that cutoff takes more than 5 minutes, all 132 would not finish in one
run, so the notebook keeps every other cutoff. The choice is saved in
`metadata.json` and reported with the results.

## Results

All 132 forecasts ran on a Kaggle T4 (`ml/artifacts/e7_forecasts/`).
The short check took 45.8 s, well under 5 minutes, so no cutoff was
dropped. One forecast took 32.9 to 45.8 s, or 1.25 GPU-hours in all,
against the estimate of 5 and the cap of 15. Peak GPU memory was
15.07 GB. The scores are in `ml/artifacts/e7_multi_day_v1/`.

The day +1 labels rebuilt from FIRMS matched the main target in every
row. The 2025 test season has 219,450 rows per lead day (22 cutoffs ×
9,975 cells).

### PR-AUC on the 2025 season

The ranges are 95% intervals.

| Score | Day +1 | Day +2 | Day +3 |
|---|---|---|---|
| Climatology | 0.321 (0.265 to 0.380) | 0.275 (0.223 to 0.332) | 0.240 (0.199 to 0.286) |
| Persistence | 0.395 (0.307 to 0.479) | 0.260 (0.198 to 0.324) | 0.210 (0.154 to 0.272) |
| Production 24-hour model, unchanged | 0.464 (0.386 to 0.539) | 0.356 (0.280 to 0.428) | 0.283 (0.228 to 0.343) |
| XGBoost without forecast values | 0.309 (0.248 to 0.372) | 0.269 (0.212 to 0.330) | 0.233 (0.185 to 0.284) |
| XGBoost with forecast values | **0.458** (0.384 to 0.532) | **0.357** (0.290 to 0.426) | 0.233 (0.185 to 0.284) |
| Fires (share of rows) | 614 (0.28%) | 747 (0.34%) | 867 (0.40%) |

### ROC-AUC on the 2025 season

| Score | Day +1 | Day +2 | Day +3 |
|---|---|---|---|
| Climatology | 0.868 (0.835 to 0.897) | 0.846 (0.820 to 0.870) | 0.836 (0.810 to 0.862) |
| Persistence | 0.906 (0.880 to 0.925) | 0.878 (0.855 to 0.899) | 0.822 (0.800 to 0.842) |
| Production 24-hour model, unchanged | 0.972 (0.964 to 0.980) | 0.952 (0.931 to 0.969) | 0.935 (0.915 to 0.952) |
| XGBoost without forecast values | 0.913 (0.887 to 0.934) | 0.868 (0.839 to 0.894) | 0.829 (0.806 to 0.854) |
| XGBoost with forecast values | 0.971 (0.961 to 0.980) | 0.955 (0.938 to 0.969) | 0.829 (0.806 to 0.854) |

### Brier score and log loss

Lower is better. Persistence gives counts, not probabilities, so it has
no Brier score or log loss.

| Score | Brier, day +1 | Brier, day +2 | Brier, day +3 | Log loss, day +1 | Log loss, day +2 | Log loss, day +3 |
|---|---:|---:|---:|---:|---:|---:|
| Climatology | 0.00223 | 0.00278 | 0.00333 | 0.0296 | 0.0399 | 0.0476 |
| Production 24-hour model, unchanged | 0.00191 | 0.00262 | 0.00323 | 0.0095 | 0.0128 | 0.0175 |
| XGBoost without forecast values | 0.00212 | 0.00271 | 0.00325 | 0.0101 | 0.0133 | 0.0170 |
| XGBoost with forecast values | 0.00192 | 0.00258 | 0.00325 | 0.0091 | 0.0125 | 0.0170 |

### What forecast values add

XGBoost with forecast values minus XGBoost without them:

| Difference | Day +1 | Day +2 | Day +3 |
|---|---|---|---|
| PR-AUC | **+0.148** (0.120 to 0.180) | **+0.088** (0.061 to 0.113) | 0.000 (0.000 to 0.000) |
| ROC-AUC | +0.058 (0.043 to 0.077) | +0.087 (0.071 to 0.105) | 0.000 (0.000 to 0.000) |
| Brier score | −0.0002 (−0.0003 to −0.0001) | −0.0001 (−0.0002 to −0.0001) | 0.0000 (0.0000 to 0.0000) |
| Log loss | −0.0010 (−0.0012 to −0.0008) | −0.0008 (−0.0014 to −0.0002) | 0.0000 (0.0000 to 0.0000) |
| Adds value by the decision rule | Yes | Yes | No |

What this shows:

- **RQ7. Forecast weather adds value on day +1 and day +2.** On both
  days, the interval of the PR-AUC difference is entirely above zero,
  and the Brier score and log loss are lower.
- **On day +3, the two models are the same.** Early stopping on the
  2023 validation season kept only the first tree of each model:
  validation PR-AUC was highest after one tree and did not improve over
  the next 10. That tree splits only on fire counts, so both models give
  the same predictions. By the decision rule, forecast weather adds no
  value on day +3. This does not show that the day +3 forecast values
  hold no information. It shows that the fixed training settings did
  not use them.
- **RQ8. Skill falls with lead time.** With forecast values, PR-AUC falls
  from 0.458 to 0.357 to 0.233, and ROC-AUC from 0.971 to 0.955 to
  0.829. ROC-AUC does not depend on the share of rows with a fire, which
  rises from 0.28% to 0.40% over the same days.
- **Against persistence**, the model with forecast values is better on
  day +1 (+0.063, 0.036 to 0.094) and day +2 (+0.096, 0.057 to 0.136),
  but not on day +3 (+0.023, −0.017 to 0.055).
- **The production 24-hour model does as well without forecast
  weather.** Used unchanged for every lead day, with the weather
  observed up to the cutoff, it scores 0.464, 0.356 and 0.283. On days
  +1 and +2 this is about the same as the model with forecast values
  (0.458 and 0.357), and on day +3 it is higher. So most of the gain on
  days +1 and +2 comes from having weather at all, not from forecast
  weather in particular. This comparison is not part of the decision
  rule, and the interval of the difference between these two models was
  not computed.
- **Calibration.** On day +1, the lowest bin holds 218,269 of the
  219,450 test rows, with a predicted rate of 0.0019 and an observed
  rate of 0.0010. The reliability plots are in
  `ml/artifacts/e7_multi_day_v1/plots/`.

## Limits

- Backtests start from ERA5 reanalysis, which is more accurate than the
  operational analysis a live forecast would start from. The results
  are likely an upper bound for live use.
- One weather model (SFNO) and one index version (the approximation
  without 2 m dew point) were tested.
- The test is one season with 22 forecast dates, so the intervals are
  wide.
- The specification fixed the XGBoost settings, so no other settings
  were tried for day +3.
- Forecast weather was not compared directly with the observed weather
  that the production model uses.

## How to run

1. Run `notebooks/e7_forecasts_on_t4.ipynb` on Kaggle and copy the
   output folder to `ml/artifacts/e7_forecasts/`.
2. Download the FIRMS days that day +2 and day +3 need (uses
   `FIRMS_MAP_KEY` from `.env`):

   ```bash
   python scripts/research/download_e7_fire_labels.py
   ```

3. Build the rows, train, and score:

   ```bash
   python scripts/research/run_e7.py
   ```

Results go to `ml/artifacts/e7_multi_day_v1/`: `config.json`,
`metrics.json`, `predictions.csv.gz`, calibration tables, reliability
plots, and the three calibrated models.

## Code

| File | Purpose |
|---|---|
| `earth2/timing.py` | Start time, lead-day windows and forecast times |
| `earth2/forecast.py` | Runs the weather model and computes the daily index values on the GPU |
| `earth2/store.py` | Saves and loads one file per cutoff |
| `earth2/e7.py` | Lead-day labels, interpolation to cells, rows, models and scores |
