import json
import os
import sys

from ai_earth_intelligence_and_forecasting_engine.query.dispatch import Backend
from ai_earth_intelligence_and_forecasting_engine.query.run_ask_earth import (
    run_ask_earth,
)
from dotenv import load_dotenv
from google import genai

load_dotenv()

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
