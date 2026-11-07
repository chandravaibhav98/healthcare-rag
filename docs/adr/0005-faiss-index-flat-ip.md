# ADR-0005 — FAISS `IndexFlatIP` over L2-normalised vectors

- **Status:** Accepted (implemented and verified in Phase 1, 2026-11-07)
- **Plan ref:** `plan.md` §3 ADR-005 · **Affects:** SC1
- **Evidence:** [spike](../spikes/2026-11-07-faiss-determinism.md) · `backend/app/rag/index/faiss_store.py`

## Context

The corpus is small (42 documents, 209 chunks). Approximate indexes add training
randomness and recall loss for no latency benefit at this size.

## Decision

- Exact cosine search with `faiss.IndexFlatIP` over L2-normalised `float32` vectors
  (faiss-cpu 1.15.1, pinned).
- Persisted with `faiss.serialize_index` and written by Python rather than with
  `faiss.write_index`, which avoids C-level file I/O with non-ASCII Windows paths. The
  bytes are hashed into the manifest.
- Search results are re-sorted by `(-round(score, 6), row)`, so ties and last-ulp BLAS
  differences cannot reorder results between platforms.
- The `VectorStore` protocol keeps the scale path open (IVF-PQ, HNSW, Qdrant, pgvector);
  the RUNBOOK will document it rather than this project building it.

## Consequences

- **Positive:** deterministic serialisation (verified across seeds and in CI), exact
  recall, no tuning.
- **Negative:** O(n) search. Revisit above roughly 10⁵–10⁶ chunks.

## Verification

`tests/unit/test_index_stores.py` (round-trip, tie-breaking, dtype guards) and the CI
cross-OS manifest comparison.
