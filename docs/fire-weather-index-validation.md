# Fire-Weather Index Validation

Can the [Hot-Dry-Windy Index](hot-dry-windy-index.md) alone tell where
a fire will start in the next 24 hours? On this grid and target, it
cannot. It ranks cells worse than chance and far worse than climatology.

## Setup

`research/fire_weather.py` and `scripts/research/validate_fire_weather_index.py`:

- **Index:** the surface approximation of the index (`surface_hdw_v1`),
  from ERA5-Land 2 m temperature, 2 m relative humidity and 10 m wind.
  ERA5-Land has no pressure levels, so the paper's 500 m layer cannot be
  used.
- **Time:** the weather at the forecast cutoff, 10:00 UTC. The paper's
  daily value is the highest of 12, 18 and 00 UTC, but those hours come
  after the cutoff, so using them would leak future weather.
- **Target and grid:** the main benchmark's target, a FIRMS fire in the 0.1° cell
  in the 24 hours after the cutoff.
- **Periods:** 2023 (validation year) and the 2025 season. The held-out
  2024 test year is not used.
- **Scores compared:**
  - climatology, fitted on 2019 to 2022;
  - the index;
  - its two parts, vapor pressure deficit (VPD) and wind speed;
  - the index's local percentile: its rank among the same cell's 2019
    to 2022 values. This removes the effect of each place's normal
    climate.
- **Intervals:** 95% intervals from the block bootstrap over forecast
  dates used in `docs/evaluation.md` (1,000 samples, fixed seed).
- **Rows:** cells without ERA5-Land values (mostly coast and water) are
  left out of every score, so all scores use the same rows.

Reproduce with:

```bash
cd ml
uv sync --group research
cd ..
python scripts/research/validate_fire_weather_index.py
```

The run takes about 90 minutes on a laptop CPU and writes
`ml/artifacts/earth2_index_validation/`.

## Result

Each period has 161,282 rows over 22 forecast dates. 2023 has 914 fire
rows (0.57%) and 2025 has 577 (0.36%).

| Score | 2023 PR-AUC | 2023 ROC-AUC | 2025 PR-AUC | 2025 ROC-AUC |
|---|---|---|---|---|
| Climatology | 0.232 (0.192 to 0.275) | 0.812 (0.784 to 0.839) | 0.317 (0.261 to 0.376) | 0.852 (0.817 to 0.884) |
| Index | 0.005 (0.004 to 0.006) | 0.449 (0.407 to 0.495) | 0.003 (0.002 to 0.003) | 0.372 (0.330 to 0.421) |
| VPD only | 0.005 (0.004 to 0.006) | 0.411 (0.369 to 0.453) | 0.003 (0.002 to 0.003) | 0.363 (0.324 to 0.402) |
| Wind only | 0.007 (0.006 to 0.008) | 0.554 (0.518 to 0.591) | 0.004 (0.003 to 0.005) | 0.478 (0.441 to 0.524) |
| Index, local percentile | 0.007 (0.005 to 0.011) | 0.532 (0.470 to 0.592) | 0.003 (0.003 to 0.004) | 0.464 (0.423 to 0.512) |

What this shows:

- **The index alone has no skill here.** Its PR-AUC is at or below the
  fire rate, and its ROC-AUC is below 0.5 in both periods.
- **Dry air points away from fires.** VPD alone ranks worst. A likely
  reason: at 10:00 UTC (3 a.m. in California) the driest air is in the
  deserts, where there is little fuel. Fires start where fuel is, and
  climatology captures that.
- **Removing place does not rescue it.** The local percentile asks
  "is today unusual for this cell?" Its intervals include 0.5 in both
  periods.
- **Climatology is better in every comparison.** Every interval of the
  difference from climatology is below zero.

The index measures weather that helps a fire spread once it burns. It
does not measure fuel or ignition, and the target here is a new
detection. So the index is used as one feature next to fire history and
geography, not as a forecast by itself.

## Limits

- Surface approximation only. The full index needs pressure levels,
  which ERA5-Land does not have.
- One time of day, before the afternoon peak of fire weather.
- 22 weekly forecast dates per period, June to October.
- FIRMS detects fires from satellites. Small or short fires can be
  missed, and the same fire can be counted on several days.
