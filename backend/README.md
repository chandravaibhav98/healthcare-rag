# backend

The FastAPI service and the RAG domain library. The full layout is in `plan.md` §2.3.

| Path | Purpose | Phase |
| --- | --- | --- |
| `app/api/schemas/` | **API contract v1** (Pydantic) | 0 ✅ |
| `app/core/config.py` | Typed settings; every key is documented in `../.env.example` | 0 ✅ |
| `evaluation/schemas.py` | Gold-dataset schema | 0 ✅ |
| `evaluation/` | Gold sets, retrieval/validation metrics, threshold sweep, CI gate ([dataset card](evaluation/datasets/DATASET_CARD.md)) | 4 ✅ |
| `openapi.json` | Committed contract snapshot; CI fails if it drifts | 0 ✅ |
| `app/rag/` | Ingestion, embeddings, index, retrieval, generation | 1–2 ✅ |
| `app/rag/validation/` | Coverage, query support, numeric gate, confidence (ADR-0002) | 3 ✅ |
| `app/services/qa_service.py` | `/qa` use case: retrieve → floor → generate → validate → decide | 3 ✅ |
| `app/api/`, `app/core/` | Routes, deps, errors; logging, metrics, middleware, rate limit | 3 ✅ |
| `app/db/`, `migrations/` | SQLAlchemy models, sessions, Alembic (SQLite + PostgreSQL) | 5 ✅ |
| `app/repositories/` | Data access with shared pagination | 5 ✅ |
| `app/services/` (auth, config, index, eval, admin, maintenance, query-log writer) | Phase 5 use cases | 5 ✅ |
| `app/api/routes/auth.py`, `app/api/routes/admin/` | Auth and admin API (RBAC per route) | 5 ✅ |
| `app/api/routes/escalations.py`, `migrations/versions/0002_*` | User escalation to the review queue (contract 1.3) | 6 ✅ |
| `app/core/security.py`, `app/core/redaction.py` | argon2id + JWT; PHI redaction before persistence | 5 ✅ |

```bash
uv sync --locked                           # create .venv from uv.lock
uv run uvicorn --factory app.main:create_app --reload   # API (needs a built index)
uv run python scripts/smoke.py --bench 200 # probe a running API
uv run python -m evaluation.run --split dev  # evaluation scorecard (add --gate in CI)
uv run python scripts/db.py upgrade        # migrate DATABASE_URL (also: current, downgrade)
uv run python scripts/seed.py --demo       # admin + demo accounts and history
uv run python scripts/maintenance.py purge # apply the query-log retention now
uv run pytest                              # tests (PostgreSQL variants: Docker or TEST_DATABASE_URL)
uv run python scripts/export_schemas.py    # regenerate openapi.json + gold.schema.json
uv run python scripts/export_schemas.py --check   # fail if the snapshots are stale
```

Use the root `scripts/` (`setup`, `lint`, `test`) for everyday work, because they are what CI runs.

Persistence tests run once per database: `[sqlite]` always, `[postgres]` when Docker is
available (Testcontainers) or `TEST_DATABASE_URL` points at an empty PostgreSQL database
that the tests may wipe. `SKIP_POSTGRES_TESTS=1` skips them explicitly.
