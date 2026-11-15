# Forecasting Demo

This demo runs the full chain against the packaged Docker container:
forecast request -> AI plan -> validation -> workflow -> data -> model
-> risk map -> calibration -> evidence. It uses the same historical
cutoff (`2024-08-10T10:00:00Z`, a weekly cutoff on the grid) as
`docs/ml-benchmark.md` and `docs/end-to-end-test-pass.md`.

## Request

```bash
curl -X POST http://localhost:8080/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "Run a wildfire risk forecast for California with cutoff 2024-08-10T10:00:00Z"}'
```

Unlike the map query in `docs/earth-intelligence-demo.md`, this request
uses the forecast tool. So it goes through `AI plan -> validation ->
workflow` before `data -> model` runs. `docs/architecture-diagram.md`
shows the two paths.

## The chain

```text
forecast request
  -> "Run a wildfire risk forecast for California with cutoff
     2024-08-10T10:00:00Z"

AI plan
  -> one Gemini call produced exactly one step:
     {"tool": "run_forecast", "input": {"cutoff": "2024-08-10T10:00:00Z",
      "region": {"kind": "named", "value": "california"}}}

validation
  -> validate_plan_or_raise accepted it (a known region, an ISO
     cutoff, and the approved run_forecast tool); an invalid plan
     never reaches dispatch

workflow
  -> dispatch_run_forecast in execute_plan sent POST /forecasts and
     polled it on the server until it finished, inside the same
     /queries request

data
  -> 8,626 FIRMS observations in the 30-day lookback window
     (2024-07-11 to 2024-08-10), ERA5 valid time 2024-08-10T10:00:00Z

model
  -> xgboost + isotonic calibration, model_version v1, trained on
     877,800 rows (88 cutoffs, 2019-06-01 to 2022-10-26)

risk map
  -> 9,975 grid cells, probability in [0.0, 1.0]

calibration
  -> a 2-bin calibration table from this forecast's run

evidence
  -> dataset wildfire_forecast:v1, region california,
     firms_window, era5_valid_time and firms_observations,
     forecast_window 2024-08-10T10:00:00Z -> 2024-08-11T10:00:00Z (24h)
```

The Ask Earth fact holds only `{forecast_id, status}`. As
`docs/ask-earth.md` explains, a `run_forecast` fact is a reference to a
job, not the map. Calling `GET /forecasts/{id}/result` with that
`forecast_id`, which is what `ForecastPanel` does, returns the risk
map, calibration and evidence above. The result is one chain from the
question to the numbers, not two separate demos.

## Notes

- **The cutoff is not new.** `2024-08-10T10:00:00Z` is the same weekly
  cutoff on the grid that `docs/ml-benchmark.md` uses for its split.
- **There are no browser screenshots.** The requests above are the same
  ones that `ForecastPanel` and `AskEarthForm` send.
