# ADR-0010 — Superseded guidance is never used as answer text

- **Status:** Accepted (implemented in Phase 2, 2026-11-07)
- **Plan ref:** `plan.md` §9 ("version-aware retrieval"); risk R8 · **Affects:** SC3, patient safety
- **Evidence:** [Phase 2 report §3](../project/phase-2-report.md)

## Context

The corpus deliberately contains superseded/current pairs whose facts conflict
(`corpus/CORPUS_CARD.md` §5). During Phase 2 the question *"How often is respirator fit
testing required?"* produced an answer that opened with "Fit testing must be repeated at
least every two years", quoted from the **superseded** 2019 WHO PPE guidance. The current
revision requires annual testing. Retrieval was correct (both versions are relevant); the
generator simply could not tell the versions apart. In a clinical setting, presenting
outdated guidance as the answer is a safety failure, not a ranking imperfection.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| A. Exclude superseded documents from the index | Simplest | Loses the audit trail; reviewers cannot see that guidance changed; retrieval metrics lose relevant chunks |
| B. Down-rank superseded chunks in retrieval | Keeps them visible | They can still win and become answer text; it is a soft rule for a hard requirement |
| **C. Keep them retrievable, but never extract answer sentences from them** | Hard guarantee for the answer; evidence and audit trail intact | If only superseded evidence is found, there is no answer (the system abstains) |

## Decision

**C.** `Chunk.superseded` is set from the document's `status` at index time. The extractive
generator skips superseded chunks when it builds candidate sentences. Superseded chunks
can still appear in retrieval results, and therefore in `citations` on an abstention, so
a reviewer can see the history. If every relevant chunk is superseded, the answer is empty
and Phase 3 returns `needs_review` (ADR-0007).

## Consequences

- **Positive:** outdated guidance cannot be presented as an answer, by construction, and
  this is covered by unit and integration tests.
- **Negative:** chunk records carry one more field, which changes `index_version`
  (accepted in Phase 2). The rule depends on correct `status` metadata, which the loader
  validates (a `superseded` document must be superseded by an existing document).
- **Follow-ups:** the UI marks superseded sources with a badge (Phase 6). The plan §9
  conflict detector could additionally flag disagreements between *current* documents.

## Verification

`tests/unit/test_extractive.py::test_superseded_guidance_is_never_answer_text` (fixture
corpus) and `tests/integration/test_retrieval_smoke.py::test_end_to_end_answer_on_real_corpus`
(the real fit-testing question must say "annually" and cite no superseded chunk).
