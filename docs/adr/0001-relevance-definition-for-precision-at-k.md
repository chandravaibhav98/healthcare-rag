# ADR-0001 — Relevance definition for Precision@K

- **Status:** Proposed. **Approval required before Phase 0 can close** (readiness Q1)
- **Date:** 2026-11-07
- **Deciders:** project owner (proposer), mentor or stakeholder (approver)
- **Plan ref:** `plan.md` §3 ADR-001, §4 Phase 4
- **Affects success criteria:** SC2 (Precision@5 ≥ 0.65)

## Context

Precision@K for one question *q* with relevant set *R(q)* is

```text
P@K(q) = |R(q) ∩ top_K(q)| / K            P@K = mean over evaluated questions
```

A perfect retriever scores `min(|R(q)|, K) / K`, so **the size of the relevant set
caps the metric**:

| Relevant chunks per question | Best possible P@5 |
| --- | --- |
| 1 (single gold chunk) | 0.20 |
| 3 | 0.60 |
| 4 | 0.80 |
| ≥ 5 | 1.00 |

Two consequences follow:

1. With one gold chunk per question, SC2 (≥ 0.65) is impossible by construction.
2. **Correction to `plan.md` §3:** the plan's "at least 3 relevant chunks" is also too
   few. If every question has exactly 3, the best possible P@5 is 0.60, still below the
   target. The *average* of `min(|R(q)|, 5)` must exceed 3.25 just for 0.65 to be
   reachable, and in practice it needs comfortable headroom above that.

The definition of "relevant" therefore decides whether SC2 can be met, and so must be
fixed and defended **before** the gold set is annotated.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| A. Chunk-level, single gold chunk | Strict, simple | Ceiling 0.20: SC2 unreachable |
| B. **Section-level**: every chunk of the gold guideline section(s) is relevant | Matches how a clinician judges "the relevant guidance"; realistic ceiling | Coarser: rewards finding the right section, not only the exact sentence |
| C. Graded (2 = answer-bearing, 1 = topically relevant) | Most informative; enables nDCG | Costs more to annotate |
| D. Document-level: any chunk of the gold document | Easiest to annotate | Too lenient; inflates P@K, so it cannot be defended |

## Decision

Adopt **B + C**, as implemented by `backend/evaluation/schemas.py`:

1. **Relevant** means a chunk has a grade (`grades` keys == `relevant_chunk_ids`).
   - **grade 2 (answer-bearing):** the chunk contains facts needed for a correct answer.
     Every answerable item needs at least one (enforced by the schema).
   - **grade 1 (topically relevant):** the chunk belongs to the same guideline section
     (same `section_path` prefix) or to a section that directly governs the question,
     but does not itself answer it.
2. **Precision@K** is binary over grade ≥ 1. **nDCG@K** uses the grades as gains.
   **Hit@K and MRR are computed on grade-2 chunks only**, so that "found the exact
   answer" is reported separately from "found the right section".
3. P@K is computed over **answerable** questions only. Unanswerable questions have no
   relevant set by definition and are scored by abstention metrics (ADR-0002).
4. Annotation target: **≥ 4 relevant chunks per answerable question** wherever the
   corpus section supports it. Phase 1 corpus authoring must produce sections long
   enough to yield at least 4 chunks for the core topics.
5. Every evaluation report states the **achievable ceiling**
   `mean_q(min(|R(q)|, K)) / K` next to P@K, so a reviewer can see the score relative
   to what was possible.
6. The gold set is pinned to an `index_version`. Phase 4 evaluation fails fast if any
   `relevant_chunk_id` is missing from the index manifest, because a re-chunked corpus
   requires re-annotation.

## Phase 4 evidence (2026-11-12)

The warning in the Context section came true. Labelled honestly with this definition:

| Question set | Relevant chunks per question | Ceiling of P@5 | Achieved P@5 | Share of ceiling |
| --- | --- | --- | --- | --- |
| v1 corpus, all 122 answerable | 2.7 | 0.54 | — | — |
| v2 corpus, dev pool | 4.5 | 0.83 | 0.60 | 73% |
| v2 corpus, test-v1 (spent) | 4.5 | 0.82 | 0.59 | 72% |
| v2 corpus, test-v2 (held out) | 3.0 | 0.58 | 0.42 | 72% |

Raw P@5 moves with the question mix (0.42–0.60), while P@5 as a share of its ceiling stays
at 0.72–0.73. **Proposal for the approver:** report the literal P@5 (as this ADR already
requires, with its ceiling) and judge SC2 on ceiling-normalised P@5, or re-base the
target to a share of the ceiling. Smaller chunks would raise the ceiling but not usefulness
(nDCG falls), so they are rejected as metric-gaming. Annotation followed §1 and §4; the
second-person spot-check (≥ 20%) is still pending.

## Consequences

- **Positive:** SC2 becomes achievable and defensible. Grade-2 metrics keep the strict
  view visible, so section-level P@5 cannot hide a weak exact-answer retriever.
- **Negative:** relevance labels can be inflated to raise P@5. Mitigation: the written
  annotation guide (`DATASET_CARD.md`, Phase 4), a second-person spot-check of ≥ 20% of
  items, and the ceiling reported next to the score.
- **Follow-ups:** `DATASET_CARD.md` annotation guide (Phase 4); chunk-count check per
  section in the Phase 1 corpus card; eval guard that the gold set and the index manifest
  agree (Phase 4).

## Verification

- Schema validators (Phase 0, `tests/unit/test_gold_schema.py`): grades == relevant set,
  ≥ 1 grade-2 chunk per answerable item, unanswerable items have an empty set.
- Phase 4 report: P@5 with bootstrap 95% CI, the ceiling, and Hit@5 / MRR on grade 2.

## Approval

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Mentor / stakeholder | | ☐ Approve ☐ Approve with changes ☐ Reject | |
