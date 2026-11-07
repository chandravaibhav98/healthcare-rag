# ADR-0004 — Hybrid retrieval: FAISS dense + BM25, fused with RRF

- **Status:** Proposed (draft; finalised in Phase 2)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-004, §4 Phase 2 · **Affects:** SC2

## Context

Hashed vectors (ADR-0003) are essentially lexical. Guideline questions are full of
acronyms (IPC, PPE, AEFI) and paraphrases. Retrieval quality determines SC2 and, through
`query_support` and `retrieval_score`, SC3.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| Dense only | Simple | Misses exact terms and acronyms |
| BM25 only | Strong lexical baseline | No subword or vector signal |
| **Dense + BM25, Reciprocal Rank Fusion (k = 60)** | No score calibration needed; robust | Two indexes to build |
| Weighted linear blend | Tunable | Needs score normalisation and calibration |

## Decision (proposed)

Hybrid **RRF (k = `RRF_K` = 60)** over FAISS and BM25, with ties broken by `chunk_id` so
ordering is deterministic. A deterministic **acronym/synonym expansion** map lives in
config (`QUERY_EXPANSION_ENABLED`). The linear blend is evaluated as an ablation in Phase 4.

## Phase 1 evidence

On an informal 10-question probe of the real corpus, BM25 placed the expected section in
its top 4 for all 10 questions, while dense-only retrieval was noisier (P@5 ≈ 0.38).
This confirms that fusion is needed (Phase 1 report §4).

## Consequences

- Fused scores are rank-based. `retrieval_score` normalises them by
  `n_retrievers / (k + 1)` (ADR-0002).
- The Phase 4 ablation table reports BM25-only, dense-only, RRF, and RRF + expansion.

## Verification

Phase 2 unit tests (fusion maths, tie-breaking); integration smoke test (≥ 9/10 questions
with the expected document in the top 5); Phase 4 ablation.
