# Architecture Decision Records

Significant decisions are recorded as ADRs: short, immutable documents that capture
the context, the options considered and the consequences of each decision. The process
is defined in [ADR-0000](0000-record-architecture-decisions.md). New ADRs start
from [`template.md`](template.md).

## Lifecycle

`Proposed` → `Accepted` → (optionally) `Superseded by ADR-NNNN` or `Deprecated`.
An accepted ADR is never rewritten. To change a decision, write a new ADR that
supersedes it.

## Index

| ADR | Title | Status | Plan ref | Due |
| --- | --- | --- | --- | --- |
| [0000](0000-record-architecture-decisions.md) | Record architecture decisions | Accepted | — | Pre-Phase 0 |
| 0001 | Relevance definition for Precision@K (section-level + graded qrels) | Planned | §3 ADR-001 | **Phase 0 — must be Accepted** |
| 0002 | Composite confidence (coverage + query support + retrieval) with numeric gate | Planned | §3 ADR-002 | **Phase 0 — must be Accepted** |
| 0003 | Deterministic 256-D signed feature-hashing embedder | Planned | §3 ADR-003 | Phase 0 draft |
| 0004 | Hybrid retrieval (FAISS + BM25, RRF k=60) | Planned | §3 ADR-004 | Phase 0 draft |
| 0005 | FAISS `IndexFlatIP` over L2-normalised vectors | Planned | §3 ADR-005 | Phase 0 draft |
| 0006 | API contract strictness and additive `meta` object | Planned | §3 ADR-006 | Phase 0 draft |
| 0007 | Abstention response policy (patient-safety posture) | Planned | §3 ADR-007 | Phase 0 draft |
| 0008 | Persistence, auth and index distribution | Planned | §3 ADR-008 | Phase 0 draft |
| 0009 | Healthcare data handling (PHI redaction, retention) | Planned | §3 ADR-009 | Phase 0 draft |

Evidence that is already available for these ADRs is listed in
[`../spikes/`](../spikes/).
