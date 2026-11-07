# backend

The FastAPI service and the RAG domain library. The full layout is in `plan.md` §2.3.

| Path | Purpose | Phase |
| --- | --- | --- |
| `app/api/schemas/` | **API contract v1** (Pydantic) | 0 ✅ |
| `app/core/config.py` | Typed settings; every key is documented in `../.env.example` | 0 ✅ |
| `evaluation/schemas.py` | Gold-dataset schema | 0 ✅ |
| `openapi.json` | Committed contract snapshot; CI fails if it drifts | 0 ✅ |
| `app/rag/` | Ingestion, embeddings, index, retrieval, generation, validation | 1–3 |
| `app/services/`, `app/repositories/` | Orchestration and persistence | 3, 5 |

```bash
uv sync --locked                           # create .venv from uv.lock
uv run pytest                              # tests
uv run python scripts/export_schemas.py    # regenerate openapi.json + gold.schema.json
uv run python scripts/export_schemas.py --check   # fail if the snapshots are stale
```

Use the root `scripts/` (`setup`, `lint`, `test`) for everyday work, because they are what CI runs.
