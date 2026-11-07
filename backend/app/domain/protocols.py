"""Ports between the RAG pipeline and its swappable implementations.

Indexing-side ports (Phase 1): Embedder, VectorStore, SparseIndex.
Query-side ports (Phase 2): Retriever, Generator, Validator (Validator is implemented in Phase 3).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from app.domain.models import GeneratedAnswer, RetrievedChunk, ValidationResult

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


class Retriever(Protocol):
    def retrieve(self, question: str, top_k: int) -> list[RetrievedChunk]:
        """Best-first hits; deterministic for a given index and question."""
        ...


class Generator(Protocol):
    def generate(self, question: str, evidence: Sequence[RetrievedChunk]) -> GeneratedAnswer:
        """Answer from `evidence` only. Every [n] marker must resolve to a citation."""
        ...


class Validator(Protocol):
    def validate(
        self, question: str, answer: GeneratedAnswer, evidence: Sequence[RetrievedChunk]
    ) -> ValidationResult: ...
