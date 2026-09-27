from __future__ import annotations

import numpy as np
import pytest

from ai_earth_intelligence_and_forecasting_engine.rag.embeddings import embed_texts
from ai_earth_intelligence_and_forecasting_engine.rag.index import (
    build_index,
    load_index,
    save_index,
)
from ai_earth_intelligence_and_forecasting_engine.rag.lexical import BM25, tokenize
from ai_earth_intelligence_and_forecasting_engine.rag.metrics import (
    first_hit_rank,
    score_retrieval,
)

TOPICS = ("calibration", "throughput", "authentication", "drift")


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class _TopicModels:
    """Embeds a text as a one-hot over TOPICS by which topic word it
    mentions, so dense search is deterministic and meaningful."""

    def __init__(self, fail_first: int = 0):
        self.calls = 0
        self.fail_first = fail_first

    def embed_content(self, model, contents, config):
        self.calls += 1
        if self.calls <= self.fail_first:
            error = RuntimeError("429 RESOURCE_EXHAUSTED")
            error.code = 429  # type: ignore[attr-defined]
            raise error
        vectors = []
        for text in contents:
            lowered = text.lower()
            values = [1.0 if topic in lowered else 0.0 for topic in TOPICS]
            vectors.append(_FakeEmbedding([*values, 0.01]))
        return _FakeResponse(vectors)


class _FakeClient:
    def __init__(self, fail_first: int = 0):
        self.models = _TopicModels(fail_first)


@pytest.fixture
def docs_dir(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ml.md").write_text(
        "# Model\n\n## Calibration\n\nIsotonic calibration maps scores to "
        "probabilities that match observed fire frequency.\n",
        encoding="utf-8",
    )
    (docs / "scaling.md").write_text(
        "# Scaling\n\n## Throughput\n\nAdding workers lowered throughput "
        "because serialization dominates.\n",
        encoding="utf-8",
    )
    (docs / "security.md").write_text(
        "# Security\n\n## Authentication\n\nThe API has no user authentication "
        "yet; it is rate limited instead.\n",
        encoding="utf-8",
    )
    return docs


def test_bm25_ranks_the_document_sharing_rare_terms_first():
    bm25 = BM25(["fire risk calibration", "worker throughput queue", "fire fire fire"])

    scores = bm25.scores("calibration of risk")

    assert int(np.argmax(scores)) == 0
    assert scores[1] == 0
    assert "the" not in tokenize("The model")


def test_the_retrieval_doc_itself_is_not_indexed(docs_dir):
    (docs_dir / "rag.md").write_text(
        "# Retrieval\n\n## Questions\n\nIsotonic calibration question.\n",
        encoding="utf-8",
    )

    index = build_index(docs_dir)

    assert not any(chunk.source.endswith("rag.md") for chunk in index.chunks)


def test_lexical_search_works_without_any_embeddings(docs_dir):
    index = build_index(docs_dir)

    passages = index.search("isotonic calibration", k=2)

    assert index.embeddings is None
    assert passages[0].chunk.source.endswith("ml.md")


def test_dense_search_finds_a_paraphrase_lexical_search_cannot(docs_dir):
    client = _FakeClient()
    index = build_index(docs_dir, client)

    lexical = index.search("do people need to log in", k=3, mode="lexical")
    dense = index.search(
        "authentication: do people need to log in", client, k=1, mode="dense"
    )

    assert lexical == []
    assert dense[0].chunk.source.endswith("security.md")
    assert index.manifest["dimensions"] == len(TOPICS) + 1


def test_hybrid_fuses_both_rankings(docs_dir):
    client = _FakeClient()
    index = build_index(docs_dir, client)

    passages = index.search("throughput of workers", client, k=3, mode="hybrid")

    assert passages[0].chunk.source.endswith("scaling.md")
    assert passages == sorted(passages, key=lambda passage: -passage.score)


def test_index_round_trips_through_disk(docs_dir, tmp_path):
    client = _FakeClient()
    index = build_index(docs_dir, client)
    save_index(index, tmp_path / "index")

    loaded = load_index(tmp_path / "index")

    assert loaded.chunks == index.chunks
    np.testing.assert_allclose(loaded.embeddings, index.embeddings)
    assert loaded.manifest == index.manifest


def test_loading_a_missing_index_says_how_to_build_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_docs_index"):
        load_index(tmp_path / "nothing")


def test_embeddings_wait_out_a_rate_limit_and_retry():
    client = _FakeClient(fail_first=2)
    waits: list[float] = []

    vectors = embed_texts(
        client, ["drift check"], "RETRIEVAL_QUERY", sleep=waits.append
    )

    assert len(waits) == 2
    assert vectors.shape == (1, len(TOPICS) + 1)
    assert np.linalg.norm(vectors[0]) == pytest.approx(1.0)


def test_unknown_search_mode_is_rejected(docs_dir):
    with pytest.raises(ValueError, match="mode"):
        build_index(docs_dir).search("x", mode="semantic")


def test_retrieval_metrics_score_ranks_of_the_first_relevant_source():
    relevant = frozenset({"docs/a.md"})
    results = [
        (["docs/a.md", "docs/b.md"], relevant),
        (["docs/b.md", "docs/c.md", "docs/a.md"], relevant),
        (["docs/b.md"], relevant),
    ]

    scores = score_retrieval(results)

    assert first_hit_rank(["docs/b.md", "docs/a.md"], relevant) == 2
    assert scores.recall_at_1 == pytest.approx(1 / 3)
    assert scores.recall_at_3 == pytest.approx(2 / 3)
    assert scores.mrr == pytest.approx((1 + 1 / 3) / 3)
