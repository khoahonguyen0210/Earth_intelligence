from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from google import genai

# gemini-embedding-2 merges a list of contents into one embedding, so a
# batch of passages would come back as a single vector.
EMBEDDING_MODEL = "gemini-embedding-001"
BATCH_SIZE = 20
RATE_LIMIT_WAIT_SECONDS = 65.0
MAX_RATE_LIMIT_RETRIES = 8


def _is_rate_limited(error: Exception) -> bool:
    return getattr(error, "code", None) == 429


def _embed_batch(
    client: genai.Client,
    batch: list[str],
    task_type: str,
    sleep: Callable[[float], Any],
) -> list[list[float]]:
    contents: Any = batch
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=contents,
                config={"task_type": task_type},
            )
        except Exception as error:
            if not _is_rate_limited(error) or attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            sleep(RATE_LIMIT_WAIT_SECONDS)
            continue
        return [list(item.values or []) for item in response.embeddings or []]
    raise AssertionError("unreachable")


def embed_texts(
    client: genai.Client,
    texts: list[str],
    task_type: str,
    sleep: Callable[[float], Any] = time.sleep,
) -> np.ndarray:
    """Unit-length embeddings, one row per text, so a dot product is the
    cosine similarity. `task_type` is RETRIEVAL_DOCUMENT for indexed
    passages and RETRIEVAL_QUERY for questions. A rate-limited batch
    (HTTP 429) waits out the per-minute quota and is retried."""
    rows: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        rows.extend(_embed_batch(client, batch, task_type, sleep))

    matrix = np.array(rows, dtype=np.float32)
    if matrix.shape[0] != len(texts):
        raise ValueError(
            f"embedding service returned {matrix.shape[0]} vectors "
            f"for {len(texts)} texts"
        )
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)
