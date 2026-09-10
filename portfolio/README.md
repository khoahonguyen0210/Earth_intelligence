# Portfolio Evidence Package

This directory records Task 18.4, the fourth task of Phase 18. It is
not a brainstorming document. It is the one place a reader unfamiliar
with the rest of this repository can find every piece of evidence the
handbook asks for, without having to know where each was produced.

## Contents

```text
portfolio/
├── README.md                      this file
├── benchmark-results.json         all four final benchmarks (Phase 16),
├── benchmark-results.csv          the same data, flat (category,
│                                   experiment, metric, value) for a
│                                   spreadsheet or pandas.read_csv
└── forecast-result-example.json   one real forecast result (risk map
                                    sample + full calibration/evidence)
```

- **Architecture diagram** — `../docs/architecture-diagram.md` (kept
  there, not copied here, so there is exactly one version to keep
  current).
- **README** — `../README.md`, the project's main entry point: what it
  is, the problem, real results, architecture, data, scientific
  method, how to run/reproduce, testing, deployment, limitations.
- **Reproduction instructions** — `../docs/reproducibility-package.md`,
  exact commands for clean setup, local services, Earth analysis,
  forecast, ML benchmark, distributed benchmark. Every command in it
  was actually run (`docs/final-clean-clone-test.md`).

## `benchmark-results.{json,csv}`

Copied verbatim from each benchmark's own locked doc (Phase 16) --
nothing recomputed or rounded differently here:

| Category | Source |
|---|---|
| `ml_benchmark` | `docs/final-ml-benchmark.md` |
| `ablation_benchmark` | `docs/final-ablation-benchmark.md` |
| `distributed_benchmark` | `docs/final-distributed-benchmark.md` |
| `planner_benchmark` | `docs/final-planner-benchmark.md` |

The CSV is machine-generated from the JSON (one `category, experiment,
metric, value` row per number), so the two files cannot drift apart.

## `forecast-result-example.json`

One real, complete forecast result (`docs/forecasting-demo.md`'s Task
18.2 run, cutoff `2024-08-10T10:00:00Z`, California): full
`model_version`, `data_cutoff`, `forecast_window`, `calibration` table,
and `evidence`, plus a **representative sample** of the real risk grid
-- the 10 highest-probability and 5 lowest-probability real cells out
of the full 9,975. The full grid is a ~3.6MB, gitignored,
regenerable artifact (`docs/reproducibility-package.md` section 4),
not committed here; this file keeps every non-grid field complete and
truncates only the grid itself, with the truncation stated in the file
(`grid_sample_note`, `grid_total_features`).

## Demo screenshots/recording — a real gap, stated honestly

This environment has no browser-automation tool, a limitation already
stated identically in `docs/ask-earth.md` (Task 14.5),
`docs/earth-intelligence-demo.md`, and `docs/forecasting-demo.md`: no
screenshot or recording of the rendered React UI exists in this
package. What exists instead, and is not a lesser substitute so much
as a different, equally real form of evidence: the exact HTTP requests
the frontend's own `client.ts` issues (`docs/earth-intelligence-demo.md`,
`docs/forecasting-demo.md`), run against the real packaged container,
with their real responses shown in full -- plus the React component
tests (`AskEarthForm.test.tsx`, `ForecastPanel.test.tsx`,
`ForecastMap.test.tsx`, `EarthQueryResultView.test.tsx`) that prove the
UI renders exactly these response shapes correctly. A reader who wants
pixels can run `docker compose up -d --build` and open
`http://localhost:5173` themselves, following
`docs/reproducibility-package.md`.
