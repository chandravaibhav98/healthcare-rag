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

| ADR | Title | Status | Criteria |
| --- | --- | --- | --- |
| [0000](0000-record-architecture-decisions.md) | Record architecture decisions | Accepted | — |
| [0001](0001-relevance-definition-for-precision-at-k.md) | Relevance definition for Precision@K (section-level + graded) | **Proposed: needs approval (Q1)** | SC2 |
| [0002](0002-composite-confidence-and-numeric-gate.md) | Composite confidence + numeric gate (revised Phases 3 and 4) | **Proposed: needs approval (Q2)** | SC3 |
| [0003](0003-deterministic-hashed-embeddings.md) | Deterministic 256-D hashed embeddings | **Accepted** (Phase 1) | SC1, SC2 |
| [0004](0004-hybrid-retrieval-rrf.md) | Hybrid retrieval (FAISS + BM25, RRF) | **Accepted** (Phase 2); ranking default amended by 0011 | SC2 |
| [0005](0005-faiss-index-flat-ip.md) | FAISS IndexFlatIP | **Accepted** (Phase 1) | SC1 |
| [0006](0006-api-contract-and-error-format.md) | API contract v1.1, additive meta, RFC 9457 errors | Proposed (v1.1 implemented Phase 3) | SC4 |
| [0007](0007-abstention-response-policy.md) | Abstention response policy | Proposed (implemented Phase 3) | SC3 |
| [0008](0008-persistence-auth-index-distribution.md) | Persistence, auth, index distribution | Proposed (Phases 5, 8, 9) | — |
| [0009](0009-healthcare-data-handling.md) | Healthcare data handling (PHI) | Proposed (Phases 0 and 3 parts implemented) | — |
| [0010](0010-superseded-guidance-not-answer-text.md) | Superseded guidance is never used as answer text | **Accepted** (Phase 2) | SC3, safety |
| [0011](0011-bm25-ranking-default.md) | BM25 ranks by default; dense vectors score relevance | **Accepted** (Phase 4) | SC2, SC3 |

**Phase 0 exit** requires ADR-0001 and ADR-0002 to be *Accepted*: fill in their Approval tables, then change their status.

Evidence that is already available for these ADRs is listed in
[`../spikes/`](../spikes/).
