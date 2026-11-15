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
| Weather model | SFNO from Earth2Studio, default package, if the T4 table shows it fits. Otherwise this page is changed before any run. |
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
Kaggle gives about 30 free GPU-hours per week. If the T4 table shows
more than 20 seconds per step, every other cutoff is dropped and that
change is written here before the run.

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
