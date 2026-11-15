# Earth Intelligence Demo

This demo runs one fixed, supported query through the full chain:
question in plain English -> data -> analysis -> map -> evidence.

## Packaging bug found and fixed

Earlier live Ask Earth checks (`docs/end-to-end-test-pass.md`) ran the
backend with `./mvnw spring-boot:run`. Running this query against the
packaged Docker container failed at once with `Cannot run program
"python" (in directory "..")`.

`backend/Dockerfile` sets `FORECAST_PYTHON_EXECUTABLE` and
`ANALYSIS_PYTHON_EXECUTABLE`, and their `_WORKDIR` versions, to the
venv inside the image. Ask Earth did not exist when the Dockerfile was
written, and its variables (`ASK_EARTH_PYTHON_EXECUTABLE` and
`ASK_EARTH_PYTHON_WORKDIR`) were never added when Ask Earth was built.
So inside the container, every `/queries` request fell back to a plain
`python` on `PATH`, which the image does not have. **Until this demo,
Ask Earth had never been shown to work inside the packaged
container.** The fix adds both variables to the existing `ENV` block in
`backend/Dockerfile`, pointing at the same `/app/ml/.venv/bin/python`
and `/app` that the forecast and analysis paths use.

## Query

```text
"Show me a map of wildfire counts across the Bay Area in August 2024"
```

Run against the rebuilt container (`docker compose up -d --build
backend`), the Gemini API and the FIRMS history:

```bash
curl -X POST http://localhost:8080/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me a map of wildfire counts across the Bay Area in August 2024"}'
curl http://localhost:8080/queries/<id>/result
```

## The chain

```text
question in plain English
  -> "Show me a map of wildfire counts across the Bay Area in August 2024"

data
  -> NASA_FIRMS:VIIRS_SNPP_SP, region bbox [-123.3, 36.9, -121.2, 38.9],
     period 2024-08-01 to 2024-09-01

analysis
  -> a plan (generate_map, region "bay area", and the model's reading
     of "August 2024" as an exact time range), dispatched against the
     FIRMS history

map
  -> a GeoJSON FeatureCollection: one polygon (the Bay Area bounding
     box), properties.value: 245, units: "fire_count"

evidence
  -> dataset, region_bbox, period_start/period_end, and the original
     query_parameters (intent: map, question, operation), all present
     and consistent with the map and the answer text
```

Grounded answer: "For the Bay Area in August 2024, there were 245
wildfires recorded (computed). This data is based on the
NASA_FIRMS:VIIRS_SNPP_SP dataset covering the period from August 1,
2024, to September 1, 2024 (computed)." Every number can be traced to
the same evidence block, and nothing is stated beyond what was
computed.

`docs/ask-earth.md` checked the same query and the same count (245)
through the API outside a container. This demo shows it working end to
end inside the packaged artifact for the first time, and fixes the one
gap between "works locally" and "works as shipped".

## Notes

- **There are no browser screenshots.** The request above is the same
  one that `AskEarthForm` sends through `frontend/src/api/client.ts`,
  against the running container, not a mock.
- **The frontend rendering is not checked again here.** The component
  tests in `EarthQueryResultView.test.tsx` already check that the
  `isMapResult` branch renders this shape correctly.
