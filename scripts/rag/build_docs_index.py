"""Chunk docs/, embed every chunk with Gemini, and save the search index.

Needs GEMINI_API_KEY. Pass --lexical-only to build a BM25-only index
without calling the API.

    python scripts/rag/build_docs_index.py
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from ai_earth_intelligence_and_forecasting_engine.rag.index import (
    DEFAULT_INDEX_DIR,
    build_index,
    save_index,
)

DOCS_DIR = Path("docs")


def main() -> None:
    load_dotenv()
    client = None if "--lexical-only" in sys.argv else genai.Client()
    index = build_index(DOCS_DIR, client)
    save_index(index, DEFAULT_INDEX_DIR)
    print(json.dumps(index.manifest, indent=2))
    print(f"saved -> {DEFAULT_INDEX_DIR}")


if __name__ == "__main__":
    main()
