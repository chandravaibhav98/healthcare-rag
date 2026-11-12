# ADR-0011 — BM25 ranks by default; dense vectors only score relevance

- **Status:** Accepted (Phase 4, 2026-11-12). Amends the ranking default of ADR-0004.
- **Date:** 2026-11-12
- **Plan ref:** `plan.md` §4 Phase 4 · **Affects:** SC2, SC3 · **Evidence:** `docs/evaluation-report.md` §3

## Context

ADR-0004 fused the 256-D hashed dense retriever and BM25 with equal RRF votes and left
the final choice to the Phase 4 dev split. On corpus v2 the dense retriever ranked worse
than BM25 on every metric, and giving it any vote in RRF lowered precision.

## Options considered

| Option | Dev P@5 | Dev Hit@5 | Notes |
| --- | --- | --- | --- |
| A. Equal-vote RRF (ADR-0004 as built) | 0.505 | 0.939 | Dense noise pushes relevant chunks out of the top 5 |
| B. Weighted RRF, dense vote 0.25–0.75 | 0.520–0.600 | 0.94–0.99 | Monotonically worse as the dense vote grows |
| **C. BM25 + query expansion only (dense vote 0)** | **0.603** | **1.000** | Simplest and best on every metric |
| D. Replace the embedder (sentence-transformer) | — | — | Breaks the "no external model" determinism goal (ADR-0003) |

## Decision

Adopt **C** through configuration, not by deleting code: `RRF_WEIGHT_DENSE=0.0`,
`RRF_WEIGHT_SPARSE=1.0`. `reciprocal_rank_fusion` now takes per-retriever weights, and a
retriever with a zero vote is not searched. The FAISS index stays:

* the validator's `retrieval_score` and the relevance floor use the dense cosine, which
  separates in-scope from out-of-scope questions (ADR-0002);
* a better embedder can be switched back into fusion by configuration alone.

## Consequences

* **Positive:** P@5 +0.10 and Hit@5 1.0 on dev; one fewer search per request.
* **Negative:** paraphrases with no shared terms rely entirely on the synonym map
  (paraphrase pass rate 0.62 on test-v2). Mitigation: keep growing the map from dev
  findings; revisit a stronger offline embedder if the determinism constraint is relaxed.

## Verification

`tests/unit/test_retrieval.py` (weighted fusion maths), `evaluation/run.py --gate`
(no regression on the dev pool), ablation table in the evaluation report.
