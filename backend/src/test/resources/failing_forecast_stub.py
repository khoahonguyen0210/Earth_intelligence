import json
import sys

print(json.dumps({"error": "synthetic failure"}))
sys.exit(1)
