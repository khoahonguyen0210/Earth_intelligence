# Earth Intelligence Demo — LOCKED

This document records Task 18.1, the first task of Phase 18. It is not
a brainstorming document. It runs one fixed, supported query through
the full chain the handbook asks for: natural-language question -> real
data -> analysis -> map -> evidence.

## A real packaging bug this demo found and fixed

Running this query against the **packaged Docker container** (not
`./mvnw spring-boot:run`, which is how every earlier live Ask Earth
verification — Task 14.5, `docs/end-to-end-test-pass.md` — was actually
run) failed immediately: `Cannot run program "python" (in directory
"..")`. `backend/Dockerfile` (Task 10.1) sets
`FORECAST_PYTHON_EXECUTABLE`/`ANALYSIS_PYTHON_EXECUTABLE` and their
`_WORKDIR` counterparts to the image's own bundled venv, but Ask Earth
(`ASK_EARTH_PYTHON_EXECUTABLE`/`ASK_EARTH_PYTHON_WORKDIR`) didn't exist
yet at Task 10.1 and was never added when Task 14.1 introduced it —
every request through `/queries` inside the container fell back to a
bare `python` on `PATH`, which this image doesn't have. **This means
Ask Earth had never actually been proven to work inside the packaged
container until this demo ran it for real and hit the gap.** Fixed by
adding both variables to `backend/Dockerfile`'s existing `ENV` block,
pointing at the same `/app/ml/.venv/bin/python` / `/app` the forecast
and analysis paths already use.

## The fixed query

```text
"Show me a map of wildfire counts across the Bay Area in August 2024"
```

Run against the rebuilt container (`docker compose up -d --build
backend`), the real Gemini API, and the real FIRMS history:

```bash
curl -X POST http://localhost:8080/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me a map of wildfire counts across the Bay Area in August 2024"}'
curl http://localhost:8080/queries/<id>/result
```

## The full chain, each link real

```text
natural-language question
  -> "Show me a map of wildfire counts across the Bay Area in August 2024"

real data
  -> NASA_FIRMS:VIIRS_SNPP_SP, region bbox [-123.3, 36.9, -121.2, 38.9],
     period 2024-08-01 to 2024-09-01

analysis
  -> a real plan (generate_map, region "bay area", the model's own
     reading of "August 2024" into an exact time range), dispatched
     against the real FIRMS history

map
  -> a real GeoJSON FeatureCollection: one polygon (the Bay Area's real
     bbox), properties.value: 245, units: "fire_count"

evidence
  -> dataset, region_bbox, period_start/period_end, and the original
     query_parameters (intent: map, question, operation) all present
     and consistent with the map and the answer text
```

Grounded answer text: *"For the Bay Area in August 2024, there were
245 wildfires recorded (computed). This data is based on the
NASA_FIRMS:VIIRS_SNPP_SP dataset covering the period from August 1,
2024, to September 1, 2024 (computed)."* — every number traceable to
the same evidence block, nothing asserted beyond what was computed.

This is the same query and the same real count (245) `docs/ask-earth.md`
(Task 14.5) already verified at the API layer outside a container; this
demo's contribution is proving it end to end **inside the actual
packaged artifact** for the first time, and fixing the one real gap
that stood between "works locally" and "works as shipped."

## What this task does not do

- **Does not add browser-automation screenshots.** As in Task 14.5,
  this environment has no browser-automation tool; the request shown
  above is the exact one `frontend/src/api/client.ts`'s `AskEarthForm`
  submits, against the real running container, not a mock.
- **Does not re-verify the frontend's own rendering of this result.**
  `EarthQueryResultView.test.tsx`'s component tests already cover that
  the `isMapResult` branch renders this exact shape correctly.
