# Forecasting Demo — LOCKED

This document records the forecasting demo. It is
not a brainstorming document. It runs the full chain the handbook asks
for -- forecast request -> AI plan -> validation -> workflow -> data ->
model -> risk map -> calibration -> evidence -- for real, against the
packaged Docker container, using the same documented historical cutoff
(`2024-08-10T10:00:00Z`, an on-grid weekly cutoff) as
`docs/ml-benchmark.md` and `docs/end-to-end-test-pass.md`.

## The request

```bash
curl -X POST http://localhost:8080/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "Run a wildfire risk forecast for California with cutoff 2024-08-10T10:00:00Z"}'
```

Unlike the earlier map-query demo, this one goes through the *forecast* tool
specifically, so it exercises `AI plan -> validation -> workflow` before
`data -> model` ever runs -- the same distinction
`docs/architecture-diagram.md` draws between the two paths.

## The full chain, each link real

```text
forecast request
  -> "Run a wildfire risk forecast for California with cutoff
     2024-08-10T10:00:00Z"

AI plan
  -> a real Gemini call produced exactly one step:
     {"tool": "run_forecast", "input": {"cutoff": "2024-08-10T10:00:00Z",
      "region": {"kind": "named", "value": "california"}}}

validation
  -> validate_plan_or_raise accepted it (a real region, a real ISO
     cutoff, the one approved run_forecast tool) -- an invalid plan
     never reaches dispatch, and this one wasn't

workflow
  -> execute_plan's dispatch_run_forecast submitted the real
     POST /forecasts and polled it to a terminal status server-side,
     inside the same /queries request

data
  -> 8,626 real FIRMS observations in the 30-day lookback window
     (2024-07-11 to 2024-08-10), real ERA5 valid time 2024-08-10T10:00:00Z

model
  -> xgboost + isotonic calibration, model_version v1, trained on
     877,800 real rows (88 cutoffs, 2019-06-01 to 2022-10-26)

risk map
  -> 9,975 real grid cells, probability in [0.0, 1.0]

calibration
  -> a real 2-bin calibration table from this forecast's own run

evidence
  -> dataset wildfire_forecast:v1, region california, the real
     firms_window/era5_valid_time/firms_observations, forecast_window
     2024-08-10T10:00:00Z -> 2024-08-11T10:00:00Z (24h)
```

The Ask Earth fact itself only ever carries `{forecast_id, status}` --
`docs/ask-earth.md` documents this deliberately: a
`run_forecast` fact is a job reference, not the map. Following that
same real `forecast_id` through `GET /forecasts/{id}/result` (the exact
call `ForecastPanel` makes) is what surfaces the risk map, calibration,
and evidence above -- one continuous, real chain from question to
number, not two unrelated demos.

## What this task does not do

- **Does not use a fabricated or rounded cutoff.** `2024-08-10T10:00:00Z`
  is the same on-grid weekly cutoff already locked in
  `docs/ml-benchmark.md`'s own training/evaluation split, reused
  here rather than a new, undocumented one.
- **Does not add browser screenshots**, for the same reason
  `docs/earth-intelligence-demo.md` does not: no browser-automation
  tool in this environment. The requests above are the exact ones
  `ForecastPanel`/`AskEarthForm` issue.
