"""Exact cosine-similarity store: FAISS `IndexFlatIP` over L2-normalised rows (ADR-0005)."""

from __future__ import annotations

import faiss
import numpy as np

from app.domain.protocols import FloatMatrix


class FaissFlatIPStore:
    def __init__(self, dim: int) -> None:
        self._dim = dim
        self._index: faiss.Index = faiss.IndexFlatIP(dim)

    @property
    def size(self) -> int:
        return int(self._index.ntotal)

    def add(self, vectors: FloatMatrix) -> None:
        if vectors.dtype != np.float32 or vectors.ndim != 2 or vectors.shape[1] != self._dim:
            raise ValueError(
                f"expected float32 (n, {self._dim}), got {vectors.dtype} {vectors.shape}"
            )
        self._index.add(np.ascontiguousarray(vectors))

    def search(self, queries: FloatMatrix, k: int) -> list[list[tuple[int, float]]]:
        k = min(k, self.size)
        if k <= 0:
            return [[] for _ in range(len(queries))]
        scores, ids = self._index.search(np.ascontiguousarray(queries, dtype=np.float32), k)
        results: list[list[tuple[int, float]]] = []
        for row_scores, row_ids in zip(scores, ids, strict=True):
            pairs = [(int(i), float(s)) for i, s in zip(row_ids, row_scores, strict=True) if i >= 0]
            # Deterministic order: score desc, then row id asc (rows follow corpus order).
            pairs.sort(key=lambda p: (-round(p[1], 6), p[0]))
            results.append(pairs)
        return results

    def to_bytes(self) -> bytes:
        # serialize_index (not write_index) avoids C-level file I/O with non-ASCII Windows paths.
        return bytes(faiss.serialize_index(self._index).tobytes())

    @classmethod
    def from_bytes(cls, data: bytes, dim: int) -> FaissFlatIPStore:
        store = cls(dim)
        store._index = faiss.deserialize_index(np.frombuffer(data, dtype=np.uint8))
        if store._index.d != dim:
            raise ValueError(f"index dimension {store._index.d} != expected {dim}")
        return store
