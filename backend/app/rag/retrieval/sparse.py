"""Sparse retrieval: Okapi BM25 over analysed (stemmed, stop-word-free) terms."""

from __future__ import annotations

from app.rag.analysis import analyze
from app.rag.pipeline import LoadedIndex


class SparseRetriever:
    def __init__(self, index: LoadedIndex) -> None:
        self._index = index

    def search(self, query_text: str, k: int) -> list[tuple[int, float]]:
        """(row, BM25 score) pairs, best first."""
        return self._index.bm25.search(analyze(query_text), k)
