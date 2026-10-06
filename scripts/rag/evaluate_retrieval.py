import json
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from ai_earth_intelligence_and_forecasting_engine.rag.embeddings import embed_texts
from ai_earth_intelligence_and_forecasting_engine.rag.eval_set import RETRIEVAL_CASES
from ai_earth_intelligence_and_forecasting_engine.rag.index import (
    SEARCH_MODES,
    load_index,
)
from ai_earth_intelligence_and_forecasting_engine.rag.metrics import (
    first_hit_rank,
    score_retrieval,
)

OUTPUT_PATH = Path("data/processed/evaluation/retrieval_v1.json")
K = 5


def main() -> None:
    load_dotenv()
    index = load_index()
    client = genai.Client()
    questions = [case.question for case in RETRIEVAL_CASES]
    vectors = embed_texts(client, questions, "RETRIEVAL_QUERY")

    report: dict[str, object] = {"index": index.manifest, "cases": len(questions)}
    misses: dict[str, list[str]] = {}
    for mode in SEARCH_MODES:
        results = []
        for case, vector in zip(RETRIEVAL_CASES, vectors, strict=True):
            passages = index.search(case.question, k=K, mode=mode, query_vector=vector)
            sources = [passage.chunk.source for passage in passages]
            results.append((sources, case.relevant))
            if first_hit_rank(sources, case.relevant) is None:
                misses.setdefault(mode, []).append(case.question)
        report[mode] = {
            key: round(value, 3) if isinstance(value, float) else value
            for key, value in asdict(score_retrieval(results)).items()
        }
    report["misses_at_5"] = misses

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"saved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
