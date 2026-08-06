import json
import sys

request = json.loads(sys.stdin.read())
print(json.dumps({"result": {"ok": True, "cutoff": request.get("cutoff")}}))
