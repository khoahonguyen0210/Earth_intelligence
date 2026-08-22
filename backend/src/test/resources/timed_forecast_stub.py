import json
import sys

# Task 13.2: the same success shape as well_behaved_forecast_stub.py, plus
# the timings_ms object the real pipeline (query/run_forecast.py) reports
# beside its result, including one malformed entry the runner must drop.
json.loads(sys.stdin.read())
print(json.dumps({
    "result": {"ok": True},
    "timings_ms": {
        "data_load": 120.5,
        "model_fit": 800,
        "model_inference": 4.25,
        "total": 930.0,
        "bogus": "not-a-number",
    },
}))
