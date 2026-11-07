"""Dense retrieval: hashed query embedding → exact inner-product search (ADR-0003/0005)."""

from __future__ import annotations

from app.rag.pipeline import LoadedIndex


class DenseRetriever:
    def __init__(self, index: LoadedIndex) -> None:
        self._index = index

    def search(self, query_text: str, k: int) -> list[tuple[int, float]]:
        """(row, cosine) pairs, best first; rows index `LoadedIndex.chunks`."""
        vector = self._index.embedder.embed([query_text])
        return self._index.vectors.search(vector, k)[0]
