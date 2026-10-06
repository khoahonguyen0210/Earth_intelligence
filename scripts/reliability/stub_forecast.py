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
