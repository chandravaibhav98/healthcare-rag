# ADR-0004 — Hybrid retrieval: FAISS dense + BM25, fused with RRF

- **Status:** Accepted (implemented in Phase 2, 2026-11-07; the linear blend is still compared in Phase 4)
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

## Phase 2 implementation and evidence

- `app/rag/retrieval/hybrid.py`: `reciprocal_rank_fusion` (pure function) and
  `HybridRetriever` with candidate depth `RETRIEVAL_CANDIDATE_K` (50) per retriever. The
  score is normalised to (0, 1] by `n_retrievers / (k + 1)`, and ties break on `chunk_id`.
- `app/rag/retrieval/query_expansions.json`: 22 acronyms (both directions) and 14 synonym
  groups, versioned.
- Smoke set (15 questions, `tests/fixtures/smoke_questions.json`), hit@5 / MRR:

  | Mode | No expansion | With expansion |
  | --- | --- | --- |
  | Dense only | 14/15 · 0.694 | 15/15 · 0.889 |
  | BM25 only | 15/15 · 0.900 | 15/15 · **0.967** |
  | **Hybrid RRF** | 15/15 · 0.856 | **15/15 · 0.933** |

  Expansion helps every mode. On this small set BM25 + expansion edges out hybrid on MRR.
  Hybrid stays the default because it was the most robust under paraphrase (dense alone
  missed "taking off PPE" without expansion), and it is the configuration the plan
  evaluates. The final choice is made on the Phase 4 dev split, not on 15 smoke questions.

## Verification

Phase 2 unit tests (fusion maths, tie-breaking); integration smoke test (≥ 9/10 questions
with the expected document in the top 5); Phase 4 ablation.
