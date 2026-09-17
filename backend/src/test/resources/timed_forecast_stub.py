import json
import sys

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
