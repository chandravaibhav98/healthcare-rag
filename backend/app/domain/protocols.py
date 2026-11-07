"""Ports between the RAG pipeline and its swappable implementations.

Phase 1 defines the indexing-side protocols. Retriever, Generator and Validator are
added in Phases 2-3 next to their first implementation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

FloatMatrix = npt.NDArray[np.float32]


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...

    def fit(self, texts: Sequence[str]) -> None:
        """Learn corpus statistics (e.g. document frequencies). Must be deterministic."""

    def embed(self, texts: Sequence[str]) -> FloatMatrix:
        """Return an (n, dim) float32 matrix of L2-normalised rows."""
        ...

    def config(self) -> dict[str, Any]:
        """Everything that changes the vectors; hashed into index_version."""
        ...


class VectorStore(Protocol):
    def add(self, vectors: FloatMatrix) -> None: ...

    def search(self, queries: FloatMatrix, k: int) -> list[list[tuple[int, float]]]:
        """Per query: (row id, similarity) pairs, best first."""
        ...

    def to_bytes(self) -> bytes: ...


class SparseIndex(Protocol):
    def search(self, query_terms: Sequence[str], k: int) -> list[tuple[int, float]]: ...

    def to_bytes(self) -> bytes: ...
