import json
import sys

print(json.dumps({"error": "the planner refused to answer: synthetic safety block"}))
sys.exit(1)
