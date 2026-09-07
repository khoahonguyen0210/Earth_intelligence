import json
import os
import sys

request = json.loads(sys.stdin.read())
print(json.dumps({
    "question": request.get("question"),
    "answer": "There were 3 fires (computed).",
    "facts": [{"step_id": "count", "category": "computed", "result": {"count": 3}, "evidence": None}],
    "outputs": {"count": {"count": 3}},
    "plan": {"steps": []},
    # Proves PythonEarthQueryRunner really set this env var, not just
    # that the process ran -- ServerPort's whole point.
    "backend_base_url_seen": os.environ.get("ASK_EARTH_BACKEND_BASE_URL"),
}))
