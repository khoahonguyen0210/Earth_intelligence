# Portfolio Evidence Package

This folder collects the project's evidence in one place, so a reader
who does not know the rest of the repository can find it.

## Contents

```text
portfolio/
├── README.md                      this file
├── benchmark-results.json         all four final benchmarks
├── benchmark-results.csv          the same data as flat rows (category,
│                                  experiment, metric, value) for a
│                                  spreadsheet or pandas.read_csv
└── forecast-result-example.json   one forecast result (a sample of the
                                   risk map and the full calibration and
                                   evidence)
```

- **Architecture diagram**: `../docs/architecture-diagram.md`. It is
  kept there and not copied here, so there is only one version to keep
  up to date.
- **README**: `../README.md`, the main entry point. It explains what the
  project does, how to run it, the architecture and the tests, and links
  to everything else.
- **Reproduction steps**: `../docs/reproducibility-package.md`, with the
  exact commands for setup, local services, Earth analysis, forecast,
  the ML benchmark and the distributed benchmark. Every command in it
  was run (`docs/clean-clone-test.md`).

## `benchmark-results.{json,csv}`

The numbers are copied as written from each benchmark's own document.
Nothing is computed again or rounded differently:

| Category | Source |
|---|---|
| `ml_benchmark` | `docs/ml-benchmark.md` |
| `ablation_benchmark` | `docs/ablation-benchmark.md` |
| `distributed_benchmark` | `docs/distributed-benchmark.md` |
| `planner_benchmark` | `docs/planner-accuracy-benchmark.md` |

The CSV is generated from the JSON (one `category, experiment, metric,
value` row per number), so the two files always agree.

## `forecast-result-example.json`

One complete forecast result, from the run in
`docs/forecasting-demo.md` (cutoff `2024-08-10T10:00:00Z`, California).
It has the full `model_version`, `data_cutoff`, `forecast_window`,
`calibration` table and `evidence`, plus a **sample** of the risk grid:
the 10 highest-probability and the 5 lowest-probability cells out of all
9,975. The full grid is about 3.6 MB; git ignores it and it can be
rebuilt (`docs/reproducibility-package.md`, section 4). This file keeps
every other field complete and shortens only the grid, and it says so
(`grid_sample_note`, `grid_total_features`).

## Screenshots and recordings

This package has no recording of the React interface. Instead, the
demos show the exact HTTP requests that the frontend's `client.ts`
sends (`docs/earth-intelligence-demo.md`, `docs/forecasting-demo.md`),
run against the packaged container, with the full responses. The React
component tests (`AskEarthForm.test.tsx`, `ForecastPanel.test.tsx`,
`ForecastMap.test.tsx`, `EarthQueryResultView.test.tsx`) show that the
interface renders these responses correctly. The README also has
screenshots of the home and results pages. To see the interface, run
`docker compose up -d --build` and open `http://localhost:5173`, as
described in `docs/reproducibility-package.md`.
