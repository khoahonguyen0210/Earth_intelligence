import json
import sys
from dataclasses import asdict

from ai_earth_intelligence_and_forecasting_engine.planner.generate_plan import (
    generate_plan,
)
from dotenv import load_dotenv
from google import genai

load_dotenv()


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "usage: run_planner_cli.py '<natural language question>'", file=sys.stderr
        )
        raise SystemExit(2)

    question = sys.argv[1]
    client = genai.Client()

    plan = generate_plan(question, client)

    print(json.dumps(asdict(plan), indent=2))


if __name__ == "__main__":
    main()
