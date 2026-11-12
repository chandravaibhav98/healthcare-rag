# Phase 3 Report — Validation & Confidence Engine + `/qa` API

- **Date:** 2026-11-12 · **Plan ref:** `plan.md` §4 Phase 3 (brief Phase 2, part 2)
- **Result:** all deliverables built and verified. **Exit criterion met:** `/qa` returns
  schema-valid JSON for answerable and unanswerable questions, and p95 latency is
  **11.1 ms** end-to-end over HTTP (target < 150 ms).
- **Needs a decision:** ADR-0002 was **revised** with Phase 3 evidence (two signal
  definitions changed; weights and τ unchanged). It still awaits mentor approval.

## 1. Deliverables

| Plan item | Status | Where |
| --- | --- | --- |
| `validation/coverage.py`, `numeric.py`, `confidence.py` with property tests | ✅ plus `tokenize.py`, `support.py`, `validator.py` | `backend/app/rag/validation/`, `tests/unit/test_validation*.py` |
| `services/qa_service.py`: retrieve → floor → generate → validate → status → log | ✅ observers for metrics and the query log; an observer failure never fails a request | `backend/app/services/` |
| `api/routes/qa.py` (`/api/v1/qa` + `/qa`), thin handlers | ✅ pipeline runs in the threadpool | `backend/app/api/routes/qa.py`, `deps.py` |
| Response model with `meta.signals` | ✅ contract **1.1.0** (additive: `Citation.superseded`, documented 429/500/503) | `backend/app/api/schemas/qa.py`, ADR-0006 Amendment 1 |
| `/healthz`, `/readyz`, `/version` | ✅ `/readyz` returns 503 until a verified index is loaded | `backend/app/api/routes/health.py` |
| Config, structlog JSON logs, request-ID middleware | ✅ pure ASGI middleware; ID validated or generated, echoed, bound to every log line | `backend/app/core/logging.py`, `middleware.py` |
| Prometheus `/metrics` (`qa_requests_total{status}`, `qa_confidence`, `qa_latency_seconds`, `qa_abstentions_total`) | ✅ plus HTTP counters by route template and `rag_index_info` | `backend/app/core/metrics.py` |
| problem+json handlers, CORS allow-list, security headers | ✅ 422/429/500/503 all carry `request_id`; strict CSP and `no-store` on API responses | `backend/app/api/errors.py`, `main.py` |
| Rate limiting | ✅ own token bucket instead of `slowapi` (ADR-0006 Amendment 1) | `backend/app/core/rate_limit.py` |
| Lifespan: load and verify the index, fail fast | ✅ `uvicorn --factory app.main:create_app`; a missing or tampered index stops start-up | `backend/app/main.py` |
| API tests: happy path, abstention, 422, bounds, alias parity | ✅ plus 429, 500, 503, CORS, headers, request IDs, metrics | `tests/api/test_qa_routes.py`, `test_platform.py` |
| OpenAPI snapshot test | ✅ regenerated for 1.1.0; checks that `/readyz` 503 is not mislabelled as problem+json | `backend/openapi.json`, `tests/contract/` |
| Scripts | ✅ `dev` (API + web, `--api-only`, `--web-only`) and `smoke` (`--bench N` checks p95) | `scripts/dev.*`, `scripts/smoke.*`, `backend/scripts/smoke.py` |

## 2. Verification

| Check | Result |
| --- | --- |
| Backend tests | **248 passed** (Phase 2: 178); line coverage 97% |
| `ruff`, `ruff format`, `mypy --strict` (87 files) | clean |
| Contract snapshots | up to date (1.1.0) |
| Smoke test against a real `uvicorn` process on the full index | all checks pass on both paths |
| Latency, 400 requests over HTTP (half answerable, half abstaining) | **p50 7.8 ms, p95 11.1 ms** |
| Real-corpus regression (`tests/integration/test_qa_corpus.py`) | 15/15 smoke questions validated and citing an expected document; 4/4 off-topic abstain |
| Determinism (SC1) | unchanged: the index build was not touched (`index_version` 097a9ef4becf) |

Example `/qa` response (abridged):

```json
{
  "answer": "... Once opened, date a multi-dose vial and discard it within 28 days unless the manufacturer specifies a different, shorter or longer, date [1].",
  "citations": [{"id": 1, "doc_id": "cdc-inj-001", "section_path": "Single-Dose and Multi-Dose Vials", "score": 1.0, "superseded": false, "...": "..."}],
  "confidence": 0.845511,
  "status": "validated",
  "meta": {"latency_ms": 7.2, "abstained": false, "reason": null,
           "signals": {"coverage": 1.0, "query_support": 1.0, "retrieval_score": 0.382, "numeric_ok": true}}
}
```

## 3. Findings and decisions

| Topic | Decision | Evidence |
| --- | --- | --- |
| `retrieval_score` | Absolute cosine (expanded question vs best cited chunk), **not** RRF | RRF top-hit median 1.00 in-scope vs 0.94 off-topic; cosine AUC 0.91 |
| Retrieval floor | 0.15, applied **before** generation; abstains with `below_retrieval_floor` and confidence 0 | Lowest in-scope cosine on the probe 0.18 |
| Query support | **IDF-weighted** and synonym-aware | Off-topic false validations 3/12 → 2/12, in-scope unchanged 20/20 |
| Weights and τ | Unchanged (0.40/0.35/0.25, 0.6) | A reweighting that scored 0/10 off-topic was found on the probe questions, so adopting it would be overfitting. It goes to the Phase 4 dev-split search |
| Abstention confidence | Real score for `low_confidence` / `numeric_mismatch`; 0 when nothing was generated | Reviewers see how close it was (ADR-0007) |
| Numeric tokens | Numbers inside identifiers are ignored ("who-ipc-004", "4.2a"); "2-dose" → `2 dose` | Found by the new unit tests; both sides use the same tokenizer |
| Rate limit vs benchmarks | `smoke --bench` fails if any request is not 200 | The first benchmark run was rate-limited: 429s answer in < 1 ms and faked a p50 of 0.7 ms |

## 4. Known limitations (input for Phase 4)

1. **Two of twelve off-topic probe questions are still validated**: "recommended dose of
   ibuprofen for back pain" and "side effects of statins". Their generic terms match
   vaccine guidance. All twelve off-topic questions contain a key term the corpus has
   never seen, against 3 of 20 in-scope ones ("order", "stick", "shot"). An
   unknown-term penalty plus the matching synonym entries is the leading candidate, to
   be decided on the dev split. Until then, the false-validation rate is the number to
   watch.
2. Coverage is about 1.0 for every extractive answer, so it contributes a constant 0.40
   (stated in ADR-0002). The discriminating work is done by query support and the
   retrieval score.
3. Noise in a question (for example a patient name) lowers IDF-weighted support and can
   cause an abstention. This fails safe and should be measured in Phase 4.
4. Rate limits are per process. With several replicas the bucket moves to Redis (ADR-0008).
5. The query log is a structured log line until the database arrives in Phase 5.

## 5. Hand-off to Phase 4

Build the gold dev/test splits (ADR-0001), then run `eval_retrieval.py`,
`eval_validation.py` and the threshold sweep. Tune the weights, τ and the floor on dev
only, and evaluate the unknown-term penalty from §4.1 there. The service already
exposes every signal in `meta.signals`, so the evaluation harness can call
`QAService.answer()` directly without HTTP.
