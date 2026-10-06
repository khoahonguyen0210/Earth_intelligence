from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ai_earth_intelligence_and_forecasting_engine.rag.chunking import (
    Chunk,
    chunk_directory,
)
from ai_earth_intelligence_and_forecasting_engine.rag.embeddings import (
    EMBEDDING_MODEL,
    embed_texts,
)
from ai_earth_intelligence_and_forecasting_engine.rag.lexical import BM25

if TYPE_CHECKING:
    from google import genai

DEFAULT_INDEX_DIR = Path("ml/artifacts/docs_index_v1")
CHUNKS_FILE = "chunks.json"
EMBEDDINGS_FILE = "embeddings.npy"
MANIFEST_FILE = "manifest.json"
RRF_K = 60
CANDIDATES = 50
SEARCH_MODES = ("lexical", "dense", "hybrid")


@dataclass(frozen=True)
class Passage:
    chunk: Chunk
    score: float


class DocsIndex:
    def __init__(
        self,
        chunks: list[Chunk],
        embeddings: np.ndarray | None,
        manifest: dict[str, Any],
    ):
        self.chunks = chunks
        self.embeddings = embeddings
        self.manifest = manifest
        self._bm25 = BM25([chunk.embedding_text() for chunk in chunks])

    def _lexical_ranking(self, query: str) -> np.ndarray:
        scores = self._bm25.scores(query)
        order = np.argsort(-scores, kind="stable")
        return order[scores[order] > 0]

    def _dense_ranking(self, query_vector: np.ndarray) -> np.ndarray:
        if self.embeddings is None:
            raise ValueError("this index has no embeddings")
        return np.argsort(-(self.embeddings @ query_vector), kind="stable")

    def search(
        self,
        query: str,
        client: genai.Client | None = None,
        k: int = 5,
        mode: str = "hybrid",
        query_vector: np.ndarray | None = None,
    ) -> list[Passage]:
        if mode not in SEARCH_MODES:
            raise ValueError(f"mode must be one of {SEARCH_MODES}, got {mode!r}")
        can_embed = query_vector is not None or client is not None
        if mode == "lexical" or self.embeddings is None or not can_embed:
            ranking = self._lexical_ranking(query)[:k]
            scores = self._bm25.scores(query)
            return [Passage(self.chunks[i], float(scores[i])) for i in ranking]

        if query_vector is None:
            assert client is not None
            query_vector = embed_texts(client, [query], "RETRIEVAL_QUERY")[0]
        if mode == "dense":
            similarity = self.embeddings @ query_vector
            ranking = self._dense_ranking(query_vector)[:k]
            return [Passage(self.chunks[i], float(similarity[i])) for i in ranking]

        fused: dict[int, float] = {}
        for ranking in (
            self._lexical_ranking(query)[:CANDIDATES],
            self._dense_ranking(query_vector)[:CANDIDATES],
        ):
            for rank, index in enumerate(ranking):
                fused[int(index)] = fused.get(int(index), 0.0) + 1 / (RRF_K + rank + 1)
        best = sorted(fused, key=lambda index: (-fused[index], index))[:k]
        return [Passage(self.chunks[i], fused[i]) for i in best]


def docs_fingerprint(chunks: list[Chunk]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.embedding_text().encode("utf-8"))
    return digest.hexdigest()[:16]


def _text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reusable_vectors(previous: DocsIndex | None) -> dict[str, np.ndarray]:
    if previous is None or previous.embeddings is None:
        return {}
    if previous.manifest.get("embedding_model") != EMBEDDING_MODEL:
        return {}
    return {
        _text_key(chunk.embedding_text()): vector
        for chunk, vector in zip(previous.chunks, previous.embeddings, strict=True)
    }


def build_index(
    docs_dir: Path,
    client: genai.Client | None = None,
    previous: DocsIndex | None = None,
) -> DocsIndex:
    chunks = chunk_directory(docs_dir)
    embeddings = None
    reused = 0
    if client is not None:
        known = _reusable_vectors(previous)
        texts = [chunk.embedding_text() for chunk in chunks]
        missing = [i for i, text in enumerate(texts) if _text_key(text) not in known]
        fresh = (
            embed_texts(client, [texts[i] for i in missing], "RETRIEVAL_DOCUMENT")
            if missing
            else np.zeros((0, 0), dtype=np.float32)
        )
        fresh_by_index = dict(zip(missing, fresh, strict=True))
        embeddings = np.stack(
            [
                fresh_by_index[i] if i in fresh_by_index else known[_text_key(text)]
                for i, text in enumerate(texts)
            ]
        ).astype(np.float32)
        reused = len(chunks) - len(missing)
    manifest = {
        "chunks": len(chunks),
        "documents": len({chunk.source for chunk in chunks}),
        "embedding_model": EMBEDDING_MODEL if embeddings is not None else None,
        "dimensions": int(embeddings.shape[1]) if embeddings is not None else None,
        "fingerprint": docs_fingerprint(chunks),
        "reused_embeddings": reused,
    }
    return DocsIndex(chunks, embeddings, manifest)


def save_index(index: DocsIndex, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    chunks = [asdict(chunk) for chunk in index.chunks]
    (directory / CHUNKS_FILE).write_text(json.dumps(chunks, indent=1), encoding="utf-8")
    if index.embeddings is not None:
        np.save(directory / EMBEDDINGS_FILE, index.embeddings)
    (directory / MANIFEST_FILE).write_text(
        json.dumps(index.manifest, indent=2), encoding="utf-8"
    )
    return directory


def load_index(directory: Path = DEFAULT_INDEX_DIR) -> DocsIndex:
    chunks_path = directory / CHUNKS_FILE
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"no docs index at {directory} -- run scripts/rag/build_docs_index.py first"
        )
    chunks = [
        Chunk(**entry) for entry in json.loads(chunks_path.read_text(encoding="utf-8"))
    ]
    embeddings_path = directory / EMBEDDINGS_FILE
    embeddings = np.load(embeddings_path) if embeddings_path.exists() else None
    manifest = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
    return DocsIndex(chunks, embeddings, manifest)
