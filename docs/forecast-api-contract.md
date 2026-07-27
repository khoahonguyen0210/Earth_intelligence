# Forecast API Contract — LOCKED

This document freezes the forecast API contract per Task 6.1 of the
Execution Handbook. It is not a brainstorming document. Task 6.2 (Java to
Python worker), Task 6.3 (PostGIS persistence), and Task 6.5 (Redis async
jobs) all build against this contract rather than redefining it.

This is a restatement, not a redefinition, of `PROJECT_BIBLE.md` §15's
"Java API" — Java owns request/job/result control, Python owns the
Earth-data/ML computation, exactly the boundary Task 2.7 already
established for the (non-forecast) Earth-analysis API.

## Endpoints

```text
POST /forecasts              create a forecast job, returns {forecast_id, status}
GET  /forecasts/{id}         poll job status, returns {forecast_id, status}
GET  /forecasts/{id}/result  fetch the result once status is terminal
```

`/forecasts/{id}/result` is a distinct path from Task 2.7's `/results/{id}`
(not a shared route) so the two APIs never collide, and so a forecast
result's much richer payload (below) doesn't get confused with an
analysis result.

## Request

```text
region
cutoff
```

`region` reuses the exact `RegionSpec` contract already locked in Task 2.1
(`ai_earth_intelligence_and_forecasting_engine.query.schema.RegionSpec`):
a `kind` of `"bbox"`, `"coordinates"`, or `"named"` plus a `value` whose
shape depends on `kind`. It is resolved with the same
`query.region.normalize_region` used by the Earth-analysis API, so a
forecast region and an analysis region behave identically.

`cutoff` is an ISO 8601 datetime string: the data-availability instant the
forecast is made "as of." It is parsed to a timezone-aware UTC `datetime`
the same way `query.time_range` parses a boundary. This is the same
`cutoff` concept already used throughout Phase 3/4/5
(`forecast.build_dataset.DatasetRow.cutoff`), not a new one.

## Response (`POST /forecasts`, `GET /forecasts/{id}`)

```text
forecast_id
status
```

`forecast_id` is a server-generated opaque ID (a UUID string, matching
Task 2.7's `Analysis.id` pattern).

`status` is a string. Its full value space is owned by Task 6.5:

```text
PENDING | RUNNING | SUCCEEDED | FAILED | RETRYING | CANCELLED
```

Until Task 6.5's async worker/queue exists, Task 6.2's bridge to Python is
a synchronous subprocess call (the same interim pattern
`PythonAnalysisRunner` already uses for analysis), so a request only ever
completes with a terminal `SUCCEEDED` or `FAILED` by the time it returns —
`PENDING`/`RUNNING`/`RETRYING`/`CANCELLED` are reachable only once Task 6.5
lands.

## Result (`GET /forecasts/{id}/result`)

```text
probability/risk
grid
model_version
data_cutoff
forecast_window
calibration metadata
evidence
```

`probability/risk` and `grid` are one payload, not two: a GeoJSON
`FeatureCollection` over California grid cells
(`data.grid.GridCell`/`cell_to_feature`), where each `Feature`'s
`properties` carries that cell's predicted fire-risk probability alongside
the existing `tile_id`/`lat_index`/`lon_index`/centroid properties. This
mirrors the already-locked `query.map_result` GeoJSON pattern (Task 2.5)
rather than inventing a second spatial encoding.

```text
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "CA_0421_0583",
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "properties": {
        "tile_id": "CA_0421_0583",
        "lat_index": 421,
        "lon_index": 583,
        "min_lon": ..., "min_lat": ..., "max_lon": ..., "max_lat": ...,
        "centroid_lon": ..., "centroid_lat": ...,
        "probability": 0.0374
      }
    }
  ]
}
```

`probability` is a float in `[0, 1]` — the model's predicted probability
of at least one qualifying FIRMS active-fire observation in that cell
during the forecast window, i.e. the same target `predict_*`/
`predict_calibrated` already produce in `ml/src/.../models/`. "Risk" is
the product-facing name for this same number, not a second field.

`model_version` is the string identifying which frozen model produced the
forecast (`models.calibration.MODEL_VERSION`, currently `"v1"`).

`data_cutoff` echoes the request's `cutoff`, normalized to an ISO 8601 UTC
datetime string — the result is self-describing without needing to join
back to the original request.

`forecast_window` states the window the probability applies to, derived
from the locked `forecast.spec.FORECAST_WINDOW_HOURS` (`24`):

```text
{ "start": "<data_cutoff>", "end": "<data_cutoff + 24h>", "hours": 24 }
```

`calibration metadata` is the calibration method and reliability table
already produced by Task 4.4 (`models.calibration`):

```text
{ "method": "isotonic", "table": [ {bin_index, predicted_mean, observed_frequency, count}, ... ] }
```

`evidence` reuses the exact `Evidence` shape locked for the Earth-analysis
API (`query.evidence.Evidence`/`evidence_to_dict`): `dataset`,
`period_start`, `period_end`, `region_kind`, `region_label`,
`region_bbox`, `query_parameters`, `processing_version`. `dataset` is
`"wildfire_forecast:<model_version>"`; `period_start`/`period_end` are the
forecast window's start/end (not a historical training window);
`query_parameters` records `cutoff` and `forecast_window_hours`.

## Error shape

A `FAILED` result (or a synchronous failure under Task 6.2's bridge) is:

```text
{ "error": "<message>" }
```

mirroring Task 2.7's `ErrorResponse`, returned with an HTTP `422`.

## What this document does not define

The Java-side DTOs, controller, and the actual Java-to-Python process
bridge are Task 6.2's job, not this one — exactly as Task 2.1's
`StructuredEarthQuery` contract predates and is Java-agnostic from Task
2.7's `AnalysisController`. PostGIS persistence of forecast metadata is
Task 6.3. The real async job lifecycle (Redis, retries, timeouts,
idempotency) is Tasks 6.5–6.6. This document only fixes the request,
response, and result shapes those tasks build against.
