from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by does do for from has have how in is it its of on or "
    "the this that to was what when where which who why with".split()
)
K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS]


class BM25:
    def __init__(self, documents: list[str]):
        self._terms = [Counter(tokenize(document)) for document in documents]
        self._lengths = np.array([sum(terms.values()) for terms in self._terms], float)
        self._average = float(self._lengths.mean()) if len(documents) else 0.0
        frequency: Counter[str] = Counter()
        for terms in self._terms:
            frequency.update(terms.keys())
        count = len(documents)
        self._idf = {
            term: math.log(1 + (count - seen + 0.5) / (seen + 0.5))
            for term, seen in frequency.items()
        }

    def scores(self, query: str) -> np.ndarray:
        result = np.zeros(len(self._terms))
        if not self._average:
            return result
        norm = K1 * (1 - B + B * self._lengths / self._average)
        for term in set(tokenize(query)):
            idf = self._idf.get(term)
            if idf is None:
                continue
            tf = np.array([terms.get(term, 0) for terms in self._terms], float)
            result += idf * tf * (K1 + 1) / (tf + norm)
        return result
