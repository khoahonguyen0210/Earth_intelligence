import json
import sys
from dataclasses import asdict

import anthropic

from ai_earth_intelligence_and_forecasting_engine.planner.generate_plan import (
    generate_plan,
)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "usage: run_planner_cli.py '<natural language question>'", file=sys.stderr
        )
        raise SystemExit(2)

    question = sys.argv[1]
    # Resolves ANTHROPIC_API_KEY / `ant auth login` automatically.
    client = anthropic.Anthropic()

    plan = generate_plan(question, client)

    print(json.dumps(asdict(plan), indent=2))


if __name__ == "__main__":
    main()
