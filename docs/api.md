# API reference (contract v1.3.1)

The authoritative contract is the committed OpenAPI document
[`backend/openapi.json`](../backend/openapi.json). Swagger UI is at `/docs` on a running
API, and the frontend's client is generated from it (`scripts/gen-client.sh`). This page
explains the contract and shows **real responses**, captured from the seeded E2E stack
(index `6ce73ffaf982`). Long snippets are shortened (`…`).

- Base path: `/api/v1`. The brief's `POST /qa` is an alias of `POST /api/v1/qa`.
- JSON in and out. Errors are `application/problem+json` (RFC 9457).
- Every response carries `X-Request-ID`. Send your own `X-Request-ID` to correlate.
- Versioning: v1 changes are **additive** only (new optional fields, new routes;
  ADR-0006). `GET /version` reports `contract_version`.

## 1. Endpoints

| Method and path | Purpose | Auth |
| --- | --- | --- |
| `POST /api/v1/qa` · `POST /qa` | Answer a question with validated citations | optional (required when `ALLOW_ANONYMOUS_QA=false`) |
| `POST /api/v1/escalations` | Ask for human review of an answer | optional |
| `POST /api/v1/auth/login` | E-mail + password → tokens | — |
| `POST /api/v1/auth/refresh` | Rotate the refresh token, new access token | refresh cookie |
| `POST /api/v1/auth/logout` | Revoke the session (refresh-token family) | refresh cookie |
| `GET /api/v1/auth/me` | The signed-in user | bearer |
| `GET /api/v1/admin/stats` | Volume, pass rate, confidence, latency, topics, reasons, series, histogram | reviewer |
| `GET /api/v1/admin/queries` · `/{query_id}` | Query explorer and detail (evidence, signals, withheld answer, review) | reviewer |
| `GET /api/v1/admin/reviews` · `POST /{query_id}` | Review queue and verdicts | reviewer |
| `GET /api/v1/admin/reviews/export/gold.jsonl` | Promoted reviews as gold-set candidates | reviewer |
| `GET /api/v1/admin/eval-runs` · `/{run_id}` · `POST` | Evaluation runs (dev pool only) | reviewer (POST: admin) |
| `GET /api/v1/admin/index/versions` · `POST /{version}/activate` | Index versions; hot swap | reviewer (POST: admin) |
| `GET`/`POST /api/v1/admin/index/rebuild` | Dev-only rebuild from the corpus | admin |
| `GET /api/v1/admin/documents` | Corpus inventory of the active index | reviewer |
| `GET`/`PUT /api/v1/admin/config` | Runtime threshold and weights (versioned, audited) | reviewer (PUT: admin) |
| `GET /api/v1/admin/audit-log` | Who changed what, when | admin |
| `GET /healthz` · `/readyz` · `/version` · `/metrics` | Liveness, readiness, build info, Prometheus | — |

The exact permissions are in the RBAC matrix of ADR-0008. A missing token returns 401; a
role that is too low returns 403.

## 2. `POST /api/v1/qa`

Request:

| Field | Type | Rules |
| --- | --- | --- |
| `question` | string | 3–1000 characters |
| `top_k` | integer | 1–20, default 5: chunks retrieved, and the maximum number of citations |

Response: the four fields required by the brief, plus an additive `meta`:

| Field | Meaning |
| --- | --- |
| `answer` | Extracted sentences with `[n]` markers, or the fixed abstention message |
| `citations[]` | `id` (the `n` of `[n]`), `doc_id`, `title`, `source_org`, `section_path`, `chunk_id`, `snippet`, `score`, `superseded` |
| `confidence` | 0–1, the weighted blend of the signals (ADR-0002) |
| `status` | `validated` or `needs_review` |
| `meta` | `request_id`, `index_version`, `latency_ms`, `abstained`, `reason` (`no_evidence`, `below_retrieval_floor`, `numeric_mismatch`, `low_confidence`), `signals` (`coverage`, `query_support`, `retrieval_score`, `numeric_ok`) |

### Validated

```bash
curl -s -X POST http://localhost:8000/api/v1/qa -H 'Content-Type: application/json' \
  -d '{"question": "What temperature range should refrigerated vaccines be stored at?", "top_k": 5}'
```

```json
{
  "answer": "Refrigerated vaccines must be stored between 2 °C and 8 °C, aiming for 5 °C [1]. Freeze-sensitive vaccines, including those containing aluminium adjuvants such as hepatitis B and tetanus toxoid-containing vaccines, are damaged by temperatures at or below 0 °C [2]. Wards store vaccines only in pharmacy-approved, purpose-built vaccine refrigerators that are connected to the central temperature monitoring system [3].",
  "citations": [
    {
      "id": 1,
      "doc_id": "cdc-cc-002",
      "title": "Vaccine Storage and Handling (Revised)",
      "source_org": "CDC",
      "section_path": "Temperature Ranges",
      "chunk_id": "cdc-cc-002::temperature-ranges::0001",
      "snippet": "Refrigerated vaccines must be stored between 2 °C and 8 °C, aiming for 5 °C. Frozen vaccines must be stored between −50 °C and −15 °C. …",
      "score": 1.0,
      "superseded": false
    },
    { "id": 2, "doc_id": "who-cc-001", "title": "Vaccine Cold Chain Management", "source_org": "WHO",
      "section_path": "Storage Temperatures", "chunk_id": "who-cc-001::storage-temperatures::0001",
      "snippet": "Most vaccines must be stored refrigerated between 2 °C and 8 °C. …", "score": 0.983871, "superseded": false },
    { "id": 3, "doc_id": "nih-cc-002", "title": "Ward Vaccine Refrigerator Procedure", "source_org": "NIH",
      "section_path": "Approved Units", "chunk_id": "nih-cc-002::approved-units::0001",
      "snippet": "Wards store vaccines only in pharmacy-approved, purpose-built vaccine refrigerators …", "score": 0.968254, "superseded": false }
  ],
  "confidence": 0.871319,
  "status": "validated",
  "meta": {
    "request_id": "a47959e62311474688414372e33b9e3a",
    "index_version": "6ce73ffaf982",
    "latency_ms": 16.42,
    "abstained": false,
    "reason": null,
    "signals": { "coverage": 1.0, "query_support": 1.0, "retrieval_score": 0.356597, "numeric_ok": true }
  }
}
```

### Abstained (`needs_review`)

```bash
curl -s -X POST http://localhost:8000/qa -H 'Content-Type: application/json' \
  -d '{"question": "Which antibiotic should be used for community-acquired pneumonia?", "top_k": 3}'
```

```json
{
  "answer": "The indexed guidelines do not contain sufficient evidence to answer this confidently. Please consult the cited sources or escalate for review.",
  "citations": [
    {
      "id": 1,
      "doc_id": "who-dai-002",
      "title": "Pocket Guide to Preventing Ventilator-Associated Pneumonia",
      "source_org": "WHO",
      "section_path": "Why It Matters",
      "chunk_id": "who-dai-002::why-it-matters::0001",
      "snippet": "Ventilator-associated pneumonia is a common and serious infection in intensive c…",
      "score": 1.0,
      "superseded": false
    }
  ],
  "confidence": 0.420121,
  "status": "needs_review",
  "meta": {
    "request_id": "9df210d1a6f548d284a65d918037ac71",
    "index_version": "6ce73ffaf982",
    "latency_ms": 17.206,
    "abstained": true,
    "reason": "low_confidence",
    "signals": { "coverage": 1.0, "query_support": 0.276748, "retrieval_score": 0.270361, "numeric_ok": true }
  }
}
```

The candidate answer is withheld from the caller (ADR-0007). Reviewers see it in the
review queue. Here `query_support` 0.28 shows that the cited text covers few of the
question's key terms ("antibiotic", "community-acquired").

### Validation error (422)

```bash
curl -s -X POST http://localhost:8000/api/v1/qa -H 'Content-Type: application/json' -d '{"question": "hi", "top_k": 50}'
```

```json
{
  "type": "about:blank",
  "title": "Unprocessable Entity",
  "status": 422,
  "detail": "Request validation failed.",
  "instance": "/api/v1/qa",
  "request_id": "fb6970e33e8946a387975cb3ebabc1b9",
  "errors": [
    { "loc": ["body", "question"], "msg": "String should have at least 3 characters", "type": "string_too_short" },
    { "loc": ["body", "top_k"], "msg": "Input should be less than or equal to 20", "type": "less_than_equal" }
  ]
}
```

Other errors use the same shape. Examples: 400 (malformed JSON), 401, 403
(`"Requires the 'reviewer' role."`), 404, 409, 429 (with `Retry-After`), 500 (no
internals), 503 (database not configured or not ready).

## 3. Escalation

```bash
curl -s -X POST http://localhost:8000/api/v1/escalations -H 'Content-Type: application/json' \
  -d '{"request_id": "<meta.request_id of the answer>", "note": "Not covered by our guidelines? Please check."}'
```

```json
{ "request_id": "acb594d1d3f7478c9ca3ca844b30418b", "status": "queued", "escalated_at": "2026-11-20T15:05:04.001284Z" }
```

`202 Accepted`. The answer joins the review queue with the note.

## 4. Authentication

```bash
curl -s -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email": "admin@example.org", "password": "…"}'
```

```json
{
  "token_type": "bearer",
  "access_token": "eyJhbGciOiJIUzI1…",
  "expires_in": 900,
  "refresh_expires_at": "2026-11-27T15:01:20.879758Z",
  "user": { "id": "398c0a27-…", "email": "admin@example.org", "display_name": "Admin", "role": "admin",
            "is_active": true, "created_at": "2026-11-20T15:01:13.276941Z", "last_login_at": "2026-11-20T15:01:20.879363Z" }
}
```

- Send `Authorization: Bearer <access_token>` (15 minutes by default).
- The refresh token comes as an **httpOnly cookie**. The SPA uses only the cookie.
  `/auth/refresh` rotates it; reusing an old token revokes the whole family.
- Login is rate-limited per client (`LOGIN_RATE_LIMIT`). Passwords are hashed with Argon2.

## 5. Admin examples

**Lists** share one envelope and the parameters `limit` (≤ 200), `offset`, `sort`
(an enum per list) and `order`:

```bash
curl -s "http://localhost:8000/api/v1/admin/queries?status=needs_review&limit=1" -H "Authorization: Bearer $TOKEN"
# {"items": [{"id": …, "request_id": …, "created_at": …, "question": "<redacted text>", "redactions": 0,
#   "status": "needs_review", "reason": "low_confidence", "confidence": 0.42, "top_k": 5, "latency_ms": 17.2,
#   "index_version": "6ce73ffaf982", "topics": [...], "reviewed": false, "escalated_at": null}],
#  "total": 18, "limit": 1, "offset": 0}
```

**Stats** (optional `from` and `to`, ISO 8601; default the last 7 days): `since`, `until`, `total`, `validated`, `needs_review`, `pass_rate`, `abstention_rate`, `mean_confidence`, `latency_p50_ms`,
`latency_p95_ms`, `reasons`, `top_topics`, `series`, `confidence_histogram`.

**Runtime configuration** uses optimistic locking, and every change is audited:

```bash
curl -s -X PUT http://localhost:8000/api/v1/admin/config -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"expected_version": 0,
       "values": {"threshold": 0.65, "retrieval_floor": 0.15,
                  "weights": {"coverage": 0.2, "query_support": 0.6, "retrieval": 0.2}},
       "comment": "Stricter threshold for the pilot"}'
```

```json
{ "version": 1,
  "values": { "threshold": 0.65, "retrieval_floor": 0.15, "weights": { "coverage": 0.2, "query_support": 0.6, "retrieval": 0.2 } },
  "updated_at": "2026-11-20T15:05:03.922282Z", "updated_by": "398c0a27-…", "comment": "Stricter threshold for the pilot" }
```

Saving again with `expected_version: 0` returns
`409 Conflict: "Configuration changed meanwhile (now version 1); reload and retry."`
The weights must sum to 1. Other pods apply the change within `CONFIG_POLL_SECONDS`.

## 6. Operational endpoints

```bash
curl -s http://localhost:8000/readyz
# {"status": "ready", "checks": {"index": "ok", "database": "ok"}, "index_version": "6ce73ffaf982"}
curl -s http://localhost:8000/version
# {"build_version": "0.1.0", "contract_version": "1.3.1", "index_version": "6ce73ffaf982", "analysis_version": 2}
```

`/readyz` returns 503 when the index is not loaded or the database does not answer
(`"database": "fail"`). `/healthz` is liveness only and never touches the database.
`/metrics` lists the metrics in RUNBOOK §6.1. Behind nginx and the Gateway, `/metrics`
is not exposed.

## 7. Limits

| Limit | Default | Setting |
| --- | --- | --- |
| `/qa` per client (token bucket, per pod) | 60/minute | `RATE_LIMIT_QA` |
| Login per client address | 10/minute | `LOGIN_RATE_LIMIT` |
| `top_k` | 1–20 | `RETRIEVAL_TOP_K_MAX` (cannot exceed 20) |
| Question length | 3–1000 characters | contract |
| List `limit` / `offset` | ≤ 200 / ≤ 1,000,000 | contract |
