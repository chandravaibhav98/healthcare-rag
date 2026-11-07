# ADR-0002 — Composite confidence score with a numeric-consistency gate

- **Status:** Proposed. **Approval required before Phase 0 can close** (readiness Q2)
- **Date:** 2026-11-07
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
query_support   = |K(question) ∩ C(E)| / |K(question)|
                  K = content tokens of the question; a term also counts as supported
                  if its acronym/synonym expansion appears in E (ADR-0004 map)
retrieval_score = max over cited chunks of  rrf_score / rrf_max,
                  rrf_max = n_retrievers / (k + 1)  (= 2/61 for dense + BM25, k = 60)
numeric_ok      = every numeric token in the answer also appears in E
```

### Score and status

```text
confidence = w_cov·coverage + w_qs·query_support + w_ret·retrieval_score
             defaults (.env): w = (0.40, 0.35, 0.25), sum enforced = 1.0

status = validated     iff  confidence ≥ τ (CONFIDENCE_THRESHOLD = 0.6)
                            AND numeric_ok
                            AND retrieval_score ≥ RETRIEVAL_FLOOR
         needs_review  otherwise, with meta.reason ∈ {no_evidence, below_retrieval_floor,
                                                       numeric_mismatch, low_confidence}
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
- Phase 3: property-based tests (coverage ∈ [0, 1], monotonic, empty answer → 0).
- Phase 4: pass rate ≥ 0.80 (answerable, test) and false-validation ≤ 5% as CI gates.

## Approval

| Role | Name | Decision | Date |
| --- | --- | --- | --- |
| Mentor / stakeholder | | ☐ Approve ☐ Approve with changes ☐ Reject | |
