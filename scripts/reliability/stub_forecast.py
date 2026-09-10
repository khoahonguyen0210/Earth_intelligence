"""A stand-in for scripts/query/run_forecast_cli.py whose
behaviour the reliability harness chooses per request, through the
request's own region name (a `named` region's value), so one backend
instance can run every job-level scenario:

    sleep-<n>           sleep n seconds, then succeed
    slow-once-<nonce>   the first run hangs (to be killed by the backend's
                        timeout); every later run with the same nonce
                        succeeds at once
    hang                never finish on its own
    anything else       succeed at once

Same protocol as the real CLI: the request JSON on stdin, the result JSON
on stdout (docs/forecast-api-contract.md).
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

MARKER_DIR = Path(tempfile.gettempdir()) / "ai-earth-reliability"


def main() -> None:
    request = json.loads(sys.stdin.read())
    behaviour = str(request["region"]["value"])

    if behaviour.startswith("sleep-"):
        time.sleep(float(behaviour.removeprefix("sleep-")))
    elif behaviour.startswith("slow-once-"):
        MARKER_DIR.mkdir(exist_ok=True)
        marker = MARKER_DIR / behaviour
        if not marker.exists():
            marker.write_text(str(os.getpid()), encoding="utf-8")
            time.sleep(3600)
    elif behaviour == "hang":
        time.sleep(3600)

    print(json.dumps({
        "result": {"ok": True, "behaviour": behaviour},
        "timings_ms": {"model_inference": 1.0, "total": 1.0},
    }))


if __name__ == "__main__":
    main()
