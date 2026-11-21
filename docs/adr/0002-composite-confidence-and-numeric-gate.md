# ADR-0002 — Composite confidence score with a numeric-consistency gate

- **Status:** Proposed. **Approval required** (readiness Q2). Implemented in Phase 3 as
  revised below; final numbers in `docs/evaluation-report.md`. Owner recommendation
  (Phase 12): accept
- **Date:** 2026-11-07 · **Revised:** 2026-11-12 (Revision 1: Phase 3 evidence; Revision 2: Phase 4 tuning)
- **Deciders:** project owner (proposer), mentor or stakeholder (approver)
- **Plan ref:** `plan.md` §2.2, §3 ADR-002, §4 Phases 3–4
- **Affects success criteria:** SC3 (≥ 80% validation pass rate at threshold 0.6)

## Context

The brief (D3) defines validation as **token-level overlap between the generated answer
and the retrieved guideline text**, with weakly supported answers flagged `needs_review`.

The generator is **extractive** (ADR-0004 / plan Phase 2): it copies sentences
verbatim from the retrieved chunks. Overlap between an answer and the text it was
copied from is ≈ 1.0 **by construction**, whether or not the copied sentence answers
the question. With overlap alone:

- an answer extracted from the wrong passage still scores ≈ 1.0 and is `validated`;
- the 80% pass rate (SC3) would be met trivially and would say nothing about quality;
- the abstention requirement ("abstain when confidence is low") would never trigger.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| A. Token coverage only | Literal reading of the brief | Constant for extractive answers, so it never abstains |
| B. **Composite: coverage + query support + retrieval score, with gates** | Every component can fail; deterministic; cheap; explainable | Weights must be tuned and defended |
| C. NLI / entailment model | Semantically stronger | Model download, CPU float variance (conflicts with SC1's spirit), latency |
| D. LLM-as-judge | Flexible | External API dependency, non-deterministic, cost |

## Decision

Adopt **B**. Coverage stays a first-class, reported signal, which satisfies D3 literally,
and it is combined with signals that *can* fail.

### Signals (all in [0, 1], deterministic)

```text
C(x)  = content tokens of text x: NFC, lower-case, punctuation stripped, stop-words removed,
        Snowball-stemmed; numbers with units kept as atomic tokens ("70%", "2-8 °C").
E     = concatenated text of the chunks the answer cites.

coverage        = |C(answer) ∩ C(E)| / |C(answer)|                  (0 if the answer is empty)
query_support   = Σ idf(t), t ∈ K(question) ∩ C(E)  /  Σ idf(t), t ∈ K(question)
                  K = content tokens of the question minus answer-type phrases
                  ("how long/often/soon/many/much/quickly/frequently"); a term also
                  counts as supported if an acronym/synonym alternative of its phrase
                  appears in full in E (ADR-0004 map). idf = corpus BM25 IDF; a term
                  the corpus has never seen gets the maximum IDF.        [revised]
retrieval_score = max over cited chunks of cosine(embed(expanded question), embed(chunk)),
                  clipped to [0, 1] (the same 256-D hashed space as the index) [revised]
numeric_ok      = every numeric token in the answer also appears in E
```

### Score and status

```text
confidence = w_cov·coverage + w_qs·query_support + w_ret·retrieval_score
             defaults (.env): w = (0.40, 0.35, 0.25), sum enforced = 1.0

relevance = max over the top-k hits of the same cosine as retrieval_score

if no hits                        → needs_review (no_evidence)
if relevance < RETRIEVAL_FLOOR    → needs_review (below_retrieval_floor), confidence 0,
                                    nothing is generated                       [revised]
otherwise generate, then:
status = validated     iff  confidence ≥ τ (CONFIDENCE_THRESHOLD = 0.6) AND numeric_ok
         needs_review  otherwise, reason = numeric_mismatch | low_confidence
                       (most specific first; an empty answer is no_evidence)

RETRIEVAL_FLOOR = 0.15 (absolute cosine)                                         [revised]
```

### Worked examples (defaults)

| Case | coverage | query_support | retrieval | confidence | Status |
| --- | --- | --- | --- | --- | --- |
| Right passage, well retrieved | 1.00 | 0.80 | 0.70 | **0.855** | validated |
| Wrong passage extracted | 1.00 | 0.20 | 0.50 | **0.595** | needs_review (coverage alone: 1.0 → validated ✗) |
| Corpus has no answer | 1.00 | 0.30 | 0.20 | **0.555** | needs_review |

For extractive answers, coverage contributes a near-constant 0.40. So in practice
`validated` requires `0.35·query_support + 0.25·retrieval_score ≥ 0.20`. That
requirement is what does the discriminating work, and this ADR states it explicitly
rather than leaving it hidden in the weights.

### Tuning protocol (Phase 4)

- Weights, τ and the floor are tuned on the **dev split only**. Metrics are reported on
  **test**.
- τ is chosen to maximise the pass rate on answerable questions, subject to a
  **false-validation rate ≤ 5%** on unanswerable questions. τ stays at 0.6 unless the
  data justifies a change, and the reason is documented either way.
- The report includes a sensitivity table (±0.1 per weight) and a reliability diagram.

## Revision 1 (2026-11-12): Phase 3 evidence

Implementing the validator exposed two problems with the original signal definitions.
The revision changes **how two signals are computed and where the floor is applied**.
The decision itself (option B, the weights 0.40/0.35/0.25 and τ = 0.6) is unchanged:
weights and τ are still tuned only in Phase 4, on the dev split.

**1. `retrieval_score` was rank-based and could not detect "no answer".** RRF only sees
ranks, and the top hit of *any* question has rank 1 in at least one retriever. On the
probe set the normalised RRF score of the top hit had a median of **1.00 for in-scope and
0.94 for out-of-scope** questions, so it carried almost no information. An absolute
similarity does: the cosine between the expanded question and the best chunk separated
in-scope from out-of-scope questions with **AUC 0.91** (query support: AUC 0.85). The
floor moved before generation, because there is nothing worth extracting below it, and
the response then says why (`below_retrieval_floor`) with confidence 0.

**2. Unweighted query support let generic words carry off-topic questions.** "Recommended
dose of ibuprofen for back pain?" reached 0.60 support from "recommended", "dose" and
"pain", which all occur in vaccine guidance, although the one specific term,
"ibuprofen", is absent. IDF weighting is the standard remedy: rare terms decide.

Probe results with the default weights and τ = 0.6 (smoke questions plus a few phrasing
variants and off-topic questions; **not** the gold set, which is built in Phase 4). The
original RRF-based score is not listed: with a top-hit median of 0.94 even off-topic, its
floor could not reject anything, so it was dropped before a full run.

| Configuration | In-scope validated | Out-of-scope falsely validated |
| --- | --- | --- |
| Cosine retrieval score, floor 0.15 before generation | 15/15 | 2/10 |
| ... plus IDF-weighted query support (**adopted**) | 20/20 | 2/12 |
| ... with weights (0.20, 0.45, 0.35) instead of the defaults | 15/15 | 0/10 |

The probe set grew between runs (15 + 10, then 20 + 12). On the larger set the
unweighted variant scores 20/20 and **3/12**, so IDF weighting removed one false
validation ("income tax return") without losing an in-scope answer.

The reweighted row is **not adopted**: it was chosen by looking at these very questions,
which is the overfitting the tuning protocol forbids. It is recorded as a hypothesis for
the Phase 4 dev-split search.

**Known residual (input for Phase 4).** The two remaining false validations are medication
questions ("ibuprofen dose", "statin side effects") whose generic terms match vaccine
content. Every out-of-scope probe question contains at least one key term that never
occurs in the corpus, while only 3 of 20 in-scope questions do ("order", "stick", "shot",
all everyday synonyms of corpus terms). An "unknown key term" penalty plus the matching
synonym-map entries is the leading candidate; it must be evaluated on the dev split, not
added on the strength of this probe.

## Revision 2 (2026-11-12): Phase 4 tuning

Tuned on the 144-question dev pool with 5-fold cross-validation, under constraints taken
from the brief: τ stays at 0.6 (SC3 is defined there) and coverage keeps a weight ≥ 0.2
(validation must stay coverage-based).

| Change | Before | After | Evidence (dev pool) |
| --- | --- | --- | --- |
| Question key terms | content tokens | content tokens minus 49 conversational filler words | Filler had the highest IDF in lay questions and penalised paraphrases |
| `query_support` scope | union of cited chunks | **best single cited chunk** | AUC 0.952 → 0.983 |
| Weights (coverage, support, retrieval) | 0.40, 0.35, 0.25 | **0.20, 0.60, 0.20** | CV pass 0.934, CV false validations 0.040 |
| τ, floor | 0.6, 0.15 | unchanged | Floor 0.10 gained one dev question; not worth the safety margin |

Held-out result (test-v2, one run): pass rate **0.807**, false validations **2 / 12** (both
near-domain: "hepatitis A" and "measles incubation period", evaluation report §6). A first
configuration chosen on a smaller dev split over-fitted (test-v1 pass rate 0.702) and is
documented as such. The weights remain configuration, not code.

## Consequences

- **Positive:** the pass rate becomes meaningful, abstention actually happens, and every
  `needs_review` has a machine-readable reason. Signals are exposed in
  `meta.signals` (contract v1), so the UI can explain each decision.
- **Negative:** the weights are a modelling choice. Mitigation: dev-only tuning, a
  sensitivity analysis, and configuration via `.env` without code changes.
- **Scope note:** if the optional LLM generator (Phase 2, off by default) is enabled,
  coverage stops being trivially ≈ 1 and `numeric_ok` becomes a real safety gate for
  doses and intervals. The same validator applies unchanged.

## Verification

- Contract (Phase 0): `QAResponse` rejects `validated` without citations or with
  `numeric_ok = false`; `meta.abstained` ⇔ `needs_review`; `reason` ⇔ abstained.
- Config (Phase 0): the weights must sum to 1.0; τ, floor ∈ [0, 1].
- Phase 3 ✅: property-based tests (`tests/unit/test_validation_properties.py`: coverage
  ∈ [0, 1], monotonic in evidence, empty answer → 0; numeric check; confidence bounded
  and monotonic), unit tests for every signal and reason, API tests for both paths, and
  a real-corpus regression test (`tests/integration/test_qa_corpus.py`).
- Phase 4 ✅: evaluation harness and gate (`backend/evaluation/run.py`). CI gates on "no
  regression on the dev pool and no false validations there"; the literal targets are
  reported in every run (see the evaluation report for why P@5 is not a hard gate).

## Approval

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Mentor / stakeholder | | ☐ Approve ☐ Approve with changes ☐ Reject | |
