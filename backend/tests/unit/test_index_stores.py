from __future__ import annotations

import numpy as np
import pytest

from app.rag.analysis import analyze
from app.rag.index.bm25_store import BM25Index
from app.rag.index.faiss_store import FaissFlatIPStore

DOCS = [
    "hand hygiene before gloves",
    "vaccine storage refrigerator temperature",
    "sharps container disposal",
    "vaccine cold chain temperature excursion",
]


def _unit(rows: list[list[float]]) -> np.ndarray:
    m = np.array(rows, dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def test_faiss_exact_search_and_roundtrip() -> None:
    store = FaissFlatIPStore(3)
    store.add(_unit([[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]]))
    hits = store.search(_unit([[1, 0, 0]]), 2)[0]
    assert [i for i, _ in hits] == [0, 2]
    clone = FaissFlatIPStore.from_bytes(store.to_bytes(), 3)
    assert clone.to_bytes() == store.to_bytes()
    assert clone.search(_unit([[1, 0, 0]]), 2) == store.search(_unit([[1, 0, 0]]), 2)


def test_faiss_ties_break_on_row_id() -> None:
    store = FaissFlatIPStore(2)
    store.add(_unit([[1, 0], [1, 0], [1, 0]]))
    assert [i for i, _ in store.search(_unit([[1, 0]]), 3)[0]] == [0, 1, 2]


def test_faiss_rejects_wrong_dtype_or_shape() -> None:
    store = FaissFlatIPStore(3)
    with pytest.raises(ValueError, match="float32"):
        store.add(np.zeros((1, 3), dtype=np.float64))
    with pytest.raises(ValueError, match="float32"):
        store.add(np.zeros((1, 4), dtype=np.float32))


def test_faiss_search_on_empty_index() -> None:
    assert FaissFlatIPStore(3).search(_unit([[1, 0, 0]]), 5) == [[]]


def test_bm25_ranks_term_overlap_and_is_deterministic() -> None:
    idx = BM25Index()
    idx.build([analyze(d) for d in DOCS])
    hits = idx.search(analyze("vaccine temperature"), 4)
    assert {i for i, _ in hits[:2]} == {1, 3}
    assert idx.search(analyze("unrelated words"), 4) == []
    clone = BM25Index.from_bytes(idx.to_bytes())
    assert clone.to_bytes() == idx.to_bytes()
    assert clone.search(analyze("vaccine temperature"), 4) == hits


def test_bm25_rejects_incompatible_version() -> None:
    idx = BM25Index()
    idx.build([["a"]])
    with pytest.raises(ValueError, match="incompatible"):
        BM25Index.from_bytes(idx.to_bytes().replace(b'"version":1', b'"version":2'))
