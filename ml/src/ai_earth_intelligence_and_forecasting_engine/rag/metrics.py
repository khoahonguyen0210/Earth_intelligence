from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalScores:
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    cases: int


def first_hit_rank(retrieved: list[str], relevant: frozenset[str]) -> int | None:
    """1-based rank of the first retrieved source that is relevant."""
    for rank, source in enumerate(retrieved, start=1):
        if source in relevant:
            return rank
    return None


def score_retrieval(
    results: list[tuple[list[str], frozenset[str]]],
) -> RetrievalScores:
    """`results` pairs each question's retrieved sources, best first, with
    its relevant sources. Recall@k is the share of questions with a hit
    in the top k; MRR averages 1/rank of the first hit (0 if none)."""
    ranks = [first_hit_rank(retrieved, relevant) for retrieved, relevant in results]
    count = len(ranks)

    def recall(k: int) -> float:
        return sum(1 for rank in ranks if rank is not None and rank <= k) / count

    return RetrievalScores(
        recall_at_1=recall(1),
        recall_at_3=recall(3),
        recall_at_5=recall(5),
        mrr=sum(1 / rank for rank in ranks if rank is not None) / count,
        cases=count,
    )
