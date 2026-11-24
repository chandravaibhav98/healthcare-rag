> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Backend

The FastAPI service and the RAG library behind it. Code is in `backend/`; the folder
[README](../backend/README.md) maps every path to the phase that delivered it.

## 1. Layers

```text
api/ (routes, schemas, deps, errors)      thin HTTP handlers, RBAC per route
  └─► services/ (qa, auth, admin, config, index, eval, maintenance, query-log writer)
        ├─► rag/ (domain pipeline, no web code)
        └─► repositories/ ─► db/ (SQLAlchemy models, sessions) ─► SQLite / PostgreSQL
core/   config, logging, security (JWT, Argon2id), redaction, metrics, rate limits
domain/ models and protocols: Embedder, VectorStore, SparseIndex, Retriever, Generator, Validator
```

## 2. The `/qa` pipeline (`app/rag`, `app/services/qa_service.py`)

| Step | Module | Notes |
| --- | --- | --- |
| Load and normalise | `rag/ingestion/` | Front-matter validation, NFC + LF, sorted traversal |
| Chunk | `ingestion/chunker.py` | Heading-aware; H2 is a hard boundary; tables and lists are never split |
| Embed | `rag/embeddings.py` | 256-D signed feature hashing with blake2b, float32, L2-normalised |
| Index | `rag/index/` | FAISS `IndexFlatIP`, BM25 store, `manifest.json`, version registry |
| Retrieve | `rag/retrieval/` | BM25 with concept-level query expansion; RRF fusion (dense weight 0 by default, ADR-0011) |
| Floor | `qa_service.py` | Abstain if the best evidence cosine is below `RETRIEVAL_FLOOR` (0.15) |
| Generate | `rag/generation/extractive.py` | ≤ 3 sentences, MMR, `[n]` citation markers |
| Validate | `rag/validation/` | confidence = 0.20·coverage + 0.60·query support + 0.20·retrieval score; numeric gate |
| Decide | `qa_service.py` | `validated` if confidence ≥ τ (0.6) and numbers check, else `needs_review` |
| Log | query-log writer | Redacted, asynchronous, bounded queue |

## 3. Configuration

Typed settings in `app/core/config.py`. Every key is documented in
[`.env.example`](../.env.example); a unit test fails if the two drift. Production mode
(`APP_ENV=production`) refuses a weak `JWT_SECRET`, wildcard CORS and question logging.

## 4. Running and testing

```bash
scripts/dev.sh --api-only           # uvicorn --reload on :8000
scripts/test.sh --backend           # pytest (unit, property, integration, API, contract, regression)
scripts/test.sh --backend --coverage   # app/rag ≥ 90 %, app/services ≥ 85 %, overall ≥ 80 %
scripts/eval.sh --split test        # evaluation scorecard
```

The contract snapshot is `backend/openapi.json`; CI fails if it changes without a
contract version bump. Reference: [API.md](API.md), [Database.md](Database.md),
[Data.md](Data.md), [Architecture.md](Architecture.md).
