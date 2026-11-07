# ADR-0005 — FAISS `IndexFlatIP` over L2-normalised vectors

- **Status:** Proposed (draft; finalised in Phase 1)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-005 · **Affects:** SC1
- **Evidence:** [spike 2026-11-07](../spikes/2026-11-07-faiss-determinism.md)
  (faiss-cpu 1.15.1, cp312 wheels for Linux and Windows; serialised index byte-identical across rebuilds)

## Context

The corpus is small (about 40–60 documents, a few thousand chunks). Approximate indexes
add training randomness and recall loss.

## Decision (proposed)

Exact cosine search: `IndexFlatIP` over L2-normalised `float32` vectors. Search over a few
thousand 256-D vectors takes microseconds. The `VectorStore` protocol keeps the scale path
open (IVF-PQ, HNSW, Qdrant, pgvector), and the RUNBOOK documents it rather than this
project building it.

## Consequences

- **Positive:** fully deterministic, no tuning, exact recall.
- **Negative:** O(n) search; revisit above roughly 10⁵–10⁶ chunks (RUNBOOK scaling section).

## Verification

The SHA-256 of `faiss.serialize_index` is recorded in the manifest and compared across
two builds in CI (SC1).
