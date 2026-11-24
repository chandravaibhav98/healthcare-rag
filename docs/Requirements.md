> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Requirements

What the system must do, how well, and how each requirement is verified. Source: the
project brief and [`plan.md`](../plan.md) §1.

## 1. Problem

Clinicians, administrators and support staff need fast reference answers from standard
guidelines (infection prevention and control, PPE, vaccination). Manual searching is slow
and is read differently by different people. The system answers **only from retrieved
guideline text**, cites every answer, checks the answer against its evidence, and
**abstains** when the support is weak.

## 2. Functional requirements

| ID | Requirement | Where |
| --- | --- | --- |
| FR-1 | Index a markdown guideline corpus deterministically, with no external API | `backend/app/rag/pipeline.py`, `scripts/build-index.*` |
| FR-2 | `POST /qa` takes `{question, top_k}` and returns `{answer, citations, confidence, status}` | [API.md](API.md) |
| FR-3 | `status` is `validated` or `needs_review`, decided by a confidence threshold (default 0.6) | ADR-0002, ADR-0007 |
| FR-4 | Every answer carries citations to the chunks it came from | `generation/extractive.py` |
| FR-5 | On abstention, the answer is withheld, the closest sources are still shown, and the item is queued for review | ADR-0007 |
| FR-6 | Evaluation: Precision@K, mean confidence, pass rate at the threshold, list of low-confidence queries | `backend/evaluation/`, [evaluation report](evaluation-report.md) |
| FR-7 | Reviewer workflow: review queue, approve / reject / correct, promote to the gold set | [Frontend.md](Frontend.md) |
| FR-8 | Admin: KPIs, evaluation runs, index versions, audited runtime settings, audit log | [API.md](API.md) |
| FR-9 | Users can escalate an abstained answer for review | contract 1.3 |
| FR-10 | Runbook for swapping in a secure, real guideline repository | [RUNBOOK §4](../RUNBOOK.md) |

## 3. Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-1 | Reproducible index (SC1) | Byte-identical across builds, hash seeds and OS |
| NFR-2 | Retrieval quality (SC2) | Precision@5 ≥ 0.65 on the held-out split |
| NFR-3 | Answer validation (SC3) | Pass rate ≥ 80 % at τ = 0.6 on answerable test questions |
| NFR-4 | Stable REST contract (SC4) | 0 schema violations; problem+json errors (RFC 9457) |
| NFR-5 | Safety | ≤ 5 % false validations on unanswerable questions |
| NFR-6 | Latency | `/qa` p95 < 300 ms at 50 concurrent users, 0 % 5xx |
| NFR-7 | Security | JWT + RBAC (user, reviewer, admin), Argon2id, no secrets in code or images |
| NFR-8 | Privacy | PHI redaction before persistence, question logging off in production, retention TTL (ADR-0009) |
| NFR-9 | Accessibility | WCAG 2.2 AA (axe gate on every route) |
| NFR-10 | Operability | Health/readiness probes, Prometheus metrics, structured logs with request IDs |

## 4. Constraints and assumptions

- The corpus is **synthetic** (WHO/NIH/CDC-*style*). No real guideline or patient data.
- Embeddings are 256-dimensional and computed locally (blake2b feature hashing, ADR-0003).
- The default generator is extractive and deterministic. An LLM generator is optional and off.
- Relevance for Precision@K is judged at section level (ADR-0001, awaiting sign-off).

## 5. Status against the success criteria

See the results table in the [README](../README.md#results) and the
[evaluation report](evaluation-report.md). In short: SC1, SC3 and SC4 are met. SC2 is
0.417 against a 0.65 target, because honest labels cap Precision@5 at 0.583 on the test
split. That reading is an open decision ([technical summary §5](technical-summary.md)).
