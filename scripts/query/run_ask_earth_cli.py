import json
import os
import sys

from ai_earth_intelligence_and_forecasting_engine.query.dispatch import Backend
from ai_earth_intelligence_and_forecasting_engine.query.run_ask_earth import (
    run_ask_earth,
)
from dotenv import load_dotenv
from google import genai

# Same pattern run_planner_cli.py already uses: GEMINI_API_KEY from a
# local .env (gitignored) if one exists, without a machine-wide variable.
load_dotenv()

# The real backend this same subprocess's own parent is running --
# needed for run_forecast/get_result_evidence, the two tools that go
# through the real POST /forecasts job rather than a direct Python call
# (docs/ask-earth.md). The Java caller (AskEarthController's
# PythonAskEarthRunner) sets this to the actual bound port per request;
# the default is only for running this script by hand.
BACKEND_BASE_URL = os.getenv("ASK_EARTH_BACKEND_BASE_URL", "http://localhost:8080")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        client = (
            genai.Client()
        )  # resolves GEMINI_API_KEY from .env or the real environment
        backend = Backend(base_url=BACKEND_BASE_URL)
        response = run_ask_earth(payload, client, backend)
    except Exception as error:
        json.dump({"error": str(error)}, sys.stdout)
        sys.exit(1)

    json.dump(response, sys.stdout)


if __name__ == "__main__":
    main()
