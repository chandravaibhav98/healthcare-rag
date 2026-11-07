"""Okapi BM25 sparse index (in-house, ~60 lines) with deterministic JSON persistence.

JSON is used instead of the plan's `bm25.pkl`: unpickling executes code, so a tampered
index artifact could compromise the API. JSON is also byte-stable for SC1.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from typing import Any, Final

BM25_VERSION: Final = 1


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_len: list[int] = []

    def config(self) -> dict[str, Any]:
        return {"name": "okapi-bm25", "version": BM25_VERSION, "k1": self.k1, "b": self.b}

    @property
    def size(self) -> int:
        return len(self._doc_len)

    def build(self, docs: Sequence[Sequence[str]]) -> None:
        postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_len = []
        for doc_idx, terms in enumerate(docs):
            self._doc_len.append(len(terms))
            for term, tf in sorted(Counter(terms).items()):
                postings.setdefault(term, []).append((doc_idx, tf))
        self._postings = dict(sorted(postings.items()))

    def search(self, query_terms: Sequence[str], k: int) -> list[tuple[int, float]]:
        n = self.size
        if n == 0 or k <= 0:
            return []
        avgdl = sum(self._doc_len) / n or 1.0
        scores: dict[int, float] = {}
        for term in sorted(set(query_terms)):
            plist = self._postings.get(term)
            if not plist:
                continue
            df = len(plist)
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            for doc_idx, tf in plist:
                denom = tf + self.k1 * (1 - self.b + self.b * self._doc_len[doc_idx] / avgdl)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + idf * tf * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda p: (-round(p[1], 9), p[0]))
        return ranked[:k]

    def to_bytes(self) -> bytes:
        state = {
            "config": self.config(),
            "doc_len": self._doc_len,
            "postings": {t: [list(p) for p in pl] for t, pl in self._postings.items()},
        }
        return (
            json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> BM25Index:
        state = json.loads(data)
        cfg = state["config"]
        if cfg.get("version") != BM25_VERSION:
            raise ValueError("BM25 artifact written by an incompatible version")
        idx = cls(k1=float(cfg["k1"]), b=float(cfg["b"]))
        idx._doc_len = [int(x) for x in state["doc_len"]]
        idx._postings = {
            t: [(int(d), int(f)) for d, f in pl] for t, pl in state["postings"].items()
        }
        return idx
