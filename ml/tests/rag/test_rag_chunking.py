from __future__ import annotations

from ai_earth_intelligence_and_forecasting_engine.rag.chunking import (
    MAX_CHUNK_CHARS,
    chunk_markdown,
)

DOC = """# Final ML Benchmark — LOCKED

This document freezes the final benchmark. It is not a brainstorming
document. XGBoost reached a PR-AUC of 0.4513 on the 2024 test year.

## Setup

The handbook asks for four models. Training used 2019 to 2022.

```text
handbook item     value
the handbook's example DAG
```

## Calibration

Isotonic calibration was fit on the validation split.
"""


def test_chunks_follow_headings_and_keep_their_source():
    chunks = chunk_markdown("docs/ml-benchmark.md", DOC)

    assert [chunk.heading for chunk in chunks] == [
        "Final ML Benchmark",
        "Setup",
        "Calibration",
    ]
    assert {chunk.source for chunk in chunks} == {"docs/ml-benchmark.md"}
    assert all(chunk.title == "Final ML Benchmark" for chunk in chunks)
    assert chunks[0].chunk_id == "docs/ml-benchmark.md#0"


def test_build_plan_sentences_and_words_are_removed():
    text = " ".join(chunk.text for chunk in chunk_markdown("docs/x.md", DOC))

    assert "handbook" not in text.lower()
    assert "brainstorming" not in text
    assert "This document freezes" not in text
    assert "XGBoost reached a PR-AUC of 0.4513" in text
    assert "Training used 2019 to 2022." in text
    assert "item     value" in text


def test_embedding_text_carries_title_and_heading():
    chunk = chunk_markdown("docs/x.md", DOC)[2]

    assert chunk.embedding_text().startswith("Final ML Benchmark > Calibration\n")


def test_long_sections_are_split_on_paragraphs():
    paragraphs = "\n\n".join(
        f"Paragraph {index} " + "word " * 80 for index in range(12)
    )
    chunks = chunk_markdown("docs/long.md", f"# Long\n\n## Body\n\n{paragraphs}\n")

    assert len(chunks) > 1
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert "Paragraph 0" in chunks[0].text
    assert "Paragraph 11" in chunks[-1].text
