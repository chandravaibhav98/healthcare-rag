# Rapid Query & Validation System — Delivery Plan (Setup → Deployment)

---

## 0. How to Read This Plan

| Section | Purpose |
| --- | --- |
| §1 Objectives & Success Criteria | What "done" means, with each criterion mapped to how it is verified |
| §2 Target Architecture | System view, request flow, repo layout |
| §3 Critical Cross-Cutting Decisions | Decisions that affect several phases and should be settled in Phase 0 |
| §4 Phases 0–12 | Each phase lists its objective, key decisions, a deliverables checklist and exit criteria |
| §5 Scripts Catalogue | The `scripts/` directory (bash + PowerShell parity) |
| §6 Testing Strategy | The test pyramid and the CI quality gates |
| §7 Milestones & Critical Path | Order of work and what to cut if time runs short |
| §8 Risk Register | Known risks and their mitigations |
| §9 "Above & Beyond" Backlog | Optional differentiators, clearly separated from scope |

**Guiding rule:** build a **vertical slice first**. Phases 0–4 alone satisfy every success criterion with a minimal backend. The React UI, admin dashboard, Docker, Kubernetes and the demo video are built on top of a core that already passes the targets.

---

## 1. Objectives & Success Criteria

### 1.1 Objective

A citation-first, evidence-validated question-answering service over guideline documents. It answers **only** from retrieved evidence, scores every answer for support, and **abstains** (`needs_review`) when the support is weak. It is designed so the synthetic corpus can later be swapped for the organisation's secure document gateway.

### 1.2 Success Criteria Traceability Matrix

| # | Criterion | Target | How verified | Where |
| --- | --- | --- | --- | --- |
| SC1 | Deterministic, reproducible indexing, no API dependency | 100% byte-identical rebuilds | Build the index twice and compare SHA-256 of every artifact in the manifest; runs in CI on Linux and as a manual check on Windows | `scripts/verify-determinism.*`, CI job `determinism` |
| SC2 | Retrieval Precision@5 | ≥ 0.65 | `evaluation/eval_retrieval.py` on the **held-out test split** | `docs/evaluation-report.md`, CI gate |
| SC3 | Validation pass rate @ threshold 0.6 | ≥ 80% | `evaluation/eval_validation.py` on the **answerable** subset of the test split | same |
| SC4 | Stable, REST-compliant `/qa` returning structured JSON | 0 schema violations | Pydantic response models, Schemathesis contract tests, load test with 0 5xx errors | CI jobs `contract`, `load-smoke` |
| D1 | Output `{answer, citations, confidence, status}` | Exact contract | API tests and generated OpenAPI snapshot test | `tests/api/` |
| D4 | Low-confidence query list for analysts | Generated per eval run | `evaluation/reports/<run>/low_confidence.csv` and the admin Review Queue | Admin dashboard |
| D5 | RUNBOOK covering a swap to a secure repository | Present and reviewed | Doc review checklist (Phase 12) | `RUNBOOK.md` |

---

## 2. Target Architecture

### 2.1 System Context

```text
                ┌──────────────────────────────────────────────────────┐
                │                 React SPA (Vite + TS)                │
                │  ┌──────────────────────┐  ┌───────────────────────┐ │
                │  │   Query Assistant    │  │    Admin Dashboard    │ │
                │  │ ask · cite · verify  │  │ KPIs · review · eval  │ │
                │  └──────────────────────┘  │ index · audit · config│ │
                │                            └───────────────────────┘ │
                └───────────────────────────┬──────────────────────────┘
                                            │ HTTPS (JSON, JWT)
                ┌───────────────────────────▼──────────────────────────┐
                │                 FastAPI Service (stateless)          │
                │  api/ ──► services/ ──► rag/ (domain pipeline)       │
                │                │            ├─ retrieval (hybrid)    │
                │                │            ├─ generation (extractive)│
                │                │            └─ validation (coverage) │
                │                ▼                                     │
                │          repositories/ ──► PostgreSQL                │
                │  /metrics (Prometheus) · structured JSON logs · OTel │
                └───────────────┬──────────────────────────┬───────────┘
                                │ read-only, loaded at boot │
                ┌───────────────▼─────────────┐   ┌─────────▼──────────┐
                │  Index Artifact (versioned) │   │ PostgreSQL         │
                │  index.faiss · bm25.pkl     │   │ query_log, reviews │
                │  chunks.jsonl · manifest    │   │ eval_runs, users,  │
                └───────────────▲─────────────┘   │ index_versions,    │
                                │ offline build    │ audit_log          │
                ┌───────────────┴─────────────┐   └────────────────────┘
                │  Indexing Pipeline (CLI/Job)│
                │  corpus/*.md → chunks →     │
                │  256-D hashed embeddings →  │
                │  FAISS + BM25 + manifest    │
                └─────────────────────────────┘
```

### 2.2 `/qa` Request Flow

```text
question, top_k
   │
   ├─► normalise + guard (length, top_k bounds 1..20, PHI-redaction hook)
   ├─► hybrid retrieve: dense (FAISS IP) ⊕ sparse (BM25) ─► RRF fuse ─► top_k chunks
   ├─► relevance floor check ── below floor ─► abstain (needs_review)
   ├─► extractive generator: score sentences in the top chunks → choose ≤ N sentences
   │      → compose answer with inline [n] citation markers
   ├─► validator:
   │      coverage        = |content_tokens(answer) ∩ tokens(cited evidence)| / |content_tokens(answer)|
   │      numeric check   = every number or unit in the answer appears in the cited evidence
   │      query_support   = share of the question's key terms that appear in the cited evidence
   │      retrieval_score = normalised fused score of the cited chunks
   │      confidence      = weighted blend (weights tuned in Phase 4)
   ├─► status = validated if confidence ≥ threshold (0.6) AND numeric check passes, else needs_review
   └─► persist to query_log (async, non-blocking) ─► respond
```

### 2.3 Repository Layout (monorepo)

```text
healthcare-rag/
├── backend/
│   ├── pyproject.toml · uv.lock
│   ├── app/
│   │   ├── main.py                       # app factory, lifespan (index load)
│   │   ├── api/
│   │   │   ├── deps.py                   # DI: settings, services, current_user
│   │   │   ├── errors.py                 # RFC 9457 problem+json handlers
│   │   │   ├── routes/ qa.py · health.py · auth.py · admin/*.py
│   │   │   └── schemas/ qa.py · admin.py · common.py
│   │   ├── core/ config.py · logging.py · security.py · metrics.py · tracing.py
│   │   ├── domain/ models.py · protocols.py   # Chunk, Citation, Answer, Embedder, VectorStore…
│   │   ├── rag/
│   │   │   ├── ingestion/ loader.py · normalizer.py · chunker.py
│   │   │   ├── embeddings.py                  # ← spec file: deterministic 256-D embedder
│   │   │   ├── index/ faiss_store.py · bm25_store.py · manifest.py · registry.py
│   │   │   ├── retrieval/ dense.py · sparse.py · hybrid.py
│   │   │   ├── generation/ extractive.py · llm_generator.py (optional, off by default)
│   │   │   ├── validation/ tokenize.py · coverage.py · numeric.py · confidence.py
│   │   │   └── pipeline.py                    # build_index() used by the CLI and jobs
│   │   ├── services/ qa_service.py · admin_service.py · index_service.py · eval_service.py
│   │   └── repositories/ query_log.py · reviews.py · users.py · index_versions.py · audit.py
│   ├── scripts/pipeline.py               # ← spec file: thin CLI over app.rag.pipeline
│   ├── evaluation/
│   │   ├── eval_retrieval.py             # ← spec file: P@K, R@K, MRR, nDCG, Hit@K
│   │   ├── eval_validation.py            # pass rate, mean confidence, abstention metrics
│   │   ├── threshold_sweep.py            # 0.30 → 0.90 sweep, curves, recommended threshold
│   │   ├── datasets/ gold_dev.jsonl · gold_test.jsonl · DATASET_CARD.md
│   │   └── reports/                      # gitignored run outputs (summary committed in docs/)
│   ├── migrations/                       # Alembic
│   └── tests/ unit/ · integration/ · api/ · contract/ · fixtures/
├── corpus/
│   ├── who/ · nih/ · cdc/                # synthetic *.md with YAML front-matter
│   └── CORPUS_CARD.md                    # provenance, synthetic notice, schema
├── frontend/
│   ├── src/ app/ · pages/ · features/{assistant,admin,auth}/ · components/ · api/(generated) · hooks/ · lib/
│   └── tests/                            # Vitest + RTL + MSW
├── e2e/
│   ├── playwright.config.ts              # projects: e2e (assertive) · demo (recorded)
│   ├── tests/                            # functional E2E specs
│   └── demo/                             # storyboarded demo spec + caption overlay helper
├── deploy/
│   ├── docker/ api.Dockerfile · web.Dockerfile · index.Dockerfile · nginx.conf
│   ├── compose/ docker-compose.yml · docker-compose.observability.yml
│   └── k8s/ base/ · overlays/local/ · overlays/prod/
├── scripts/                              # ops automation (.sh + .ps1), see §5
├── docs/ adr/ · architecture.md · api.md · evaluation-report.md · technical-summary.md
├── .github/workflows/ ci.yml · release.yml
├── .gitattributes · .editorconfig · .env.example
├── README.md · RUNBOOK.md · plan.md
```

**Path decision:** the spec's file names (`embeddings.py`, `scripts/pipeline.py`, `evaluation/eval_retrieval.py`) are kept **relative to `backend/`** so a reviewer can trace them. The root `scripts/` holds only shell and PowerShell ops automation.

---

## 3. Critical Cross-Cutting Decisions (settle in Phase 0, record as ADRs)

These have the biggest impact on whether the success criteria can be met. Each becomes an ADR in `docs/adr/`.

### ADR-001 — How "relevant" is defined for Precision@5 ⚠️ highest impact

**Problem:** if each question has exactly one relevant chunk, the **maximum possible P@5 is 0.20**, so the 0.65 target cannot be reached by construction.

| Option | Effect |
| --- | --- |
| A. Chunk-level, single gold chunk | P@5 ≤ 0.20. Rejected. |
| B. **Section-level qrels**: every chunk under the gold document section(s) counts as relevant | Realistic, and matches how a clinician judges "relevant guidance" |
| C. Graded qrels (2 = answer-bearing, 1 = topically relevant) | Most rigorous; supports nDCG; costs more to annotate |

**Recommendation:** use **B as the primary metric, with graded labels (C) stored alongside** so nDCG can be reported too. Annotate a set of relevant chunk IDs per question, at least 3 where the corpus supports it. Write the definition into `DATASET_CARD.md` and the evaluation report so the number can be defended.

### ADR-002 — Confidence is more than raw token coverage ⚠️

**Problem:** an extractive answer copies sentences verbatim, so its token coverage is about 1.0 **by construction**. Coverage alone would mark an answer `validated` even when the wrong passage was extracted. The 80% pass rate would be meaningless, and a reviewer will notice.

**Recommendation:** keep token-level coverage as the spec requires, and blend it with signals that can fail:

```text
confidence = w1·coverage + w2·query_support + w3·retrieval_score
hard gates: numeric_consistency must pass; retrieval_score ≥ floor
defaults:   w = (0.4, 0.35, 0.25), floor tuned in Phase 4
```

- `query_support` catches a fluent answer to the wrong question.
- `retrieval_score` catches a corpus that simply has no answer.
- `numeric_consistency` is a healthcare-specific safety check (doses, intervals, temperatures, durations): any number in the answer must appear in its cited evidence.

Weights and threshold are tuned on the **dev split only** and reported on the **test split**, to avoid overfitting.

### ADR-003 — Deterministic 256-D embeddings

| Option | Deterministic? | Corpus-independent? | Quality | Notes |
| --- | --- | --- | --- | --- |
| **A. Signed feature hashing** (word uni+bigrams + char 3–5-grams) → 256-D, sublinear TF × IDF, L2-norm | ✅ | ✅ (except IDF) | Lexical-plus | Recommended |
| B. TF-IDF → TruncatedSVD(256, fixed seed) | ⚠️ BLAS/solver variance across platforms | ❌ refit on every corpus change | Some semantics (LSA) | Good comparison baseline |
| C. Local sentence-transformer, projected to 256-D | ⚠️ CPU float variance; model download | ✅ | Best semantics | Breaks the spirit of "no external dependency" |

**Recommendation:** **A as the production embedder**, with B implemented behind the same `Embedder` protocol as an ablation in the evaluation report. Requirements for determinism:

- Use `hashlib.blake2b` (keyed by a fixed salt) for hashing. **Never Python's `hash()`**, which is salted per process via `PYTHONHASHSEED`.
- Use float32 throughout, sort input files by path, and normalise text to NFC and LF line endings.
- Pin `faiss-cpu`, NumPy and the Python minor version in `uv.lock`. Record all three in the manifest.

### ADR-004 — Retrieval strategy

Pure hashed-vector search is essentially lexical and will struggle on paraphrases. **Recommendation: hybrid retrieval** combining FAISS dense search with BM25 (`rank-bm25` or a small in-house implementation), fused with **Reciprocal Rank Fusion** (k = 60). Ties break on `chunk_id` so ordering is deterministic. Optional extras: deterministic query expansion from a small synonym and acronym map (`IPC ↔ infection prevention and control`, `PPE ↔ personal protective equipment`). In a healthcare corpus with heavy acronym use this is cheap and effective.

### ADR-005 — FAISS index type

**`IndexFlatIP` over L2-normalised vectors** (exact cosine). For a corpus of a few thousand chunks, exact search costs microseconds and is fully deterministic. The scale path (IVF-PQ, HNSW, or an external store such as Qdrant or pgvector) sits behind the `VectorStore` protocol and is documented in the RUNBOOK rather than built.

### ADR-006 — API contract strictness

- The four spec fields stay **top-level and exactly named**: `answer`, `citations`, `confidence`, `status ∈ {validated, needs_review}`.
- Extra information goes into an **additive, optional `meta` object** (`request_id`, `latency_ms`, `index_version`, `signals{coverage, query_support, retrieval_score, numeric_ok}`, `abstained`, `reason`). Adding fields is backward-compatible under REST conventions.
- Routes: the canonical route is `POST /api/v1/qa`, with `POST /qa` as an alias kept for spec compliance. Both appear in OpenAPI.
- Errors use RFC 9457 `application/problem+json`.

### ADR-007 — What is returned on abstention (patient-safety posture)

When `needs_review` is returned:

- `answer` is a standard abstention message ("The indexed guidelines do not contain sufficient evidence to answer this confidently. Please consult the cited sources or escalate for review.").
- `citations` still contains the best candidate sources, so the user can read them.
- The low-confidence candidate answer is stored for **reviewers** and shown only to the reviewer and admin roles.

This keeps the system citation-first without ever presenting weakly supported clinical text as an answer.

### ADR-008 — Persistence, auth, index distribution

| Concern | Recommendation | Alternative |
| --- | --- | --- |
| Database | PostgreSQL (SQLAlchemy 2.0 async + Alembic); SQLite only in unit tests | SQLite everywhere (simpler, but weak for concurrency and k8s) |
| Auth | Local JWT (access + refresh), RBAC roles `user`, `reviewer`, `admin`, behind an `AuthProvider` protocol ready for OIDC | Keycloak/OIDC from day one (heavier) |
| Public `/qa` access | Requires auth by default; anonymous access controlled by a config flag for the demo | — |
| Index distribution (k8s) | **Index as an OCI image** (`rag-index:<corpus_hash>`), copied by an init container into an `emptyDir` | PVC plus a build Job (mutable, harder to roll back) |
| Cache / queue | **None initially.** Add Redis only when rate limiting must work across replicas | Redis from the start (no current need) |

### ADR-009 — Healthcare data handling

Even with a synthetic corpus, users could type real patient information into questions. Therefore:

- Logging of the question text is configurable (`LOG_QUESTION_TEXT=false` in prod).
- A PHI-redaction hook runs before persistence (regex rules for MRN, phone, email and date-of-birth patterns).
- The query log has a retention TTL.
- Logs never contain secrets.

---

## 4. Phases

> Effort is indicative for one engineer: **S** ≈ ½–1 day · **M** ≈ 2–3 days · **L** ≈ 4–5 days.
> Tests are written **within** each phase. Phase 7 consolidates and hardens them.

---

### Phase 0 — Foundations, Contracts & Decisions · *S–M*

**Objective:** set up the repository, toolchain, contracts and decision records so that later phases do not churn.

**Key decisions**

- ADR-001 to ADR-009 above (draft all of them; finalise ADR-001 and ADR-002 now).
- Tooling: `uv` for Python 3.12; current Node LTS with `npm`; `ruff` + `mypy --strict` for the backend packages; ESLint + Prettier + `tsc --noEmit` for the frontend.
- Task-runner policy: **`scripts/` is the source of truth.** An optional `Makefile` only wraps the scripts, so there is no duplicated logic.
- Branching: trunk-based development with short-lived feature branches and Conventional Commits.

**Deliverables checklist**

- [ ] Monorepo skeleton per §2.3, with `.gitattributes` (`* text=auto eol=lf`; `corpus/** eol=lf` is **required for determinism**) and `.editorconfig`
- [ ] `backend/pyproject.toml` with pinned dependencies and `uv.lock`; `frontend/package.json` with lockfile
- [ ] Pre-commit hooks: ruff, ruff-format, mypy, eslint, prettier, end-of-file and trailing-whitespace fixers, detect-secrets
- [ ] `.env.example` with every config key documented
- [ ] `docs/adr/0001…0009` drafted
- [ ] **API contract v1** written as Pydantic schemas and exported as an `openapi.json` snapshot
- [ ] Gold-dataset schema defined (`{id, question, relevant_chunk_ids[], grades{}, answerable, expected_keywords[], split}`)
- [ ] `scripts/setup.*` and `scripts/lib/common.*` (see §5)
- [ ] CI skeleton: lint + typecheck + unit tests on every PR
- [ ] README stub with the project purpose and the synthetic-corpus disclaimer

**Exit criteria:** `scripts/setup.sh` and `scripts/setup.ps1` bring a clean machine to "lint and tests green", and ADR-001 and ADR-002 are approved.

---

### Phase 1 — Synthetic Corpus & Deterministic Indexing · *M* (spec Phase 1)

**Objective:** a realistic synthetic corpus and a byte-reproducible index build.

**Key decisions**

- **Corpus size and shape:** about 40–60 documents (WHO-, NIH- and CDC-style, roughly equal), covering IPC, hand hygiene, PPE donning and doffing, respiratory precautions, sterilisation, sharps, vaccination schedules, cold chain, adverse event reporting, outbreak response and waste management. Include **deliberate near-duplicates and conflicting versions** (for example two versions of a PPE guideline with different effective dates) so retrieval and citation behaviour are tested properly.
- **Front-matter schema:** `doc_id, title, source_org, version, effective_date, topic[], audience, jurisdiction, synthetic: true`.
- **Chunking:** heading-aware markdown chunking that keeps `section_path` (H1 › H2 › H3). Target 180–350 tokens with about 15% sentence overlap. Never split tables or numbered procedure lists mid-step.
- **Chunk ID:** `doc_id::section_slug::ordinal`, which is stable and human-readable, together with a `content_sha256`.
- **Corpus authoring:** written once (manually, or LLM-assisted offline) and **committed**. It is never regenerated at build time, because that would break determinism.

**Deliverables checklist**

- [ ] `corpus/` populated, plus `CORPUS_CARD.md` (provenance, synthetic statement, schema, topic coverage table)
- [ ] `ingestion/loader.py`: front-matter validation (Pydantic), sorted traversal, NFC and LF normalisation
- [ ] `ingestion/chunker.py`: heading-aware, list- and table-safe, with overlap
- [ ] `rag/embeddings.py`: `HashingEmbedder(dim=256)` with blake2b, signed hashing, sublinear TF × IDF and L2 normalisation; `SvdEmbedder` as an ablation
- [ ] `index/faiss_store.py` (`IndexFlatIP`), `index/bm25_store.py`, deterministic tie-breaking
- [ ] `index/manifest.py`: `manifest.json` with corpus hash, per-file hashes, embedder config hash, library versions, chunk count, artifact SHA-256s and `index_version = short(corpus_hash + config_hash)`
- [ ] `backend/scripts/pipeline.py` CLI: `build`, `verify`, `inspect`
- [ ] `scripts/build-index.*` and `scripts/verify-determinism.*`
- [ ] Unit tests: chunker edge cases, embedder determinism (same input gives identical bytes; different `PYTHONHASHSEED` gives the same output), manifest integrity
- [ ] CI job `determinism`: two clean builds produce identical hashes

**Exit criteria:** SC1 passes in CI, and `pipeline.py inspect` shows sensible chunks for every document.

---

### Phase 2 — Retrieval & Extractive QA Core · *M* (spec Phase 2, part 1)

**Objective:** hybrid retrieval and a citation-carrying extractive answer generator, as a pure domain library with no web code.

**Key decisions**

- **Fusion:** RRF (k = 60) versus a weighted linear score blend. Start with RRF, which needs no calibration, and evaluate both in Phase 4.
- **Sentence selection for answers:** score = BM25(sentence, query) + cosine(sentence, query) + section-title boost, with up to N sentences (default 3) and an MMR-style redundancy penalty. Sentences are output in their original document order.
- **Citation granularity:** a chunk-level citation carries `{doc_id, title, source_org, section_path, chunk_id, snippet, score}`. Sentence character offsets are kept for UI highlighting.
- **LLM generator:** defined behind a `Generator` protocol and **disabled by default**, which keeps the system deterministic and free of API dependencies. It is optional and goes through the same validator.

**Deliverables checklist**

- [ ] `domain/protocols.py`: `Embedder`, `VectorStore`, `SparseIndex`, `Retriever`, `Generator`, `Validator`
- [ ] `retrieval/hybrid.py` with RRF, a `top_k` guard and deterministic ordering
- [ ] Optional acronym and synonym query expansion (deterministic map in config)
- [ ] `generation/extractive.py`: sentence splitter (with medical-abbreviation-safe rules for "e.g.", "approx.", "Fig."), scorer, MMR, citation markers
- [ ] `IndexRegistry`: loads the active index version and swaps it atomically in memory
- [ ] Unit tests: fusion maths, tie-breaking, sentence splitting, citation integrity (every `[n]` marker resolves to a citation)
- [ ] Integration test: build the fixture corpus, then a question returns the expected `doc_id` in the top 5

**Exit criteria:** on a smoke set of about 10 questions, the expected document appears in the top 5 for at least 9.

---

### Phase 3 — Validation & Confidence Engine + `/qa` API · *M* (spec Phase 2, part 2)

**Objective:** a production-shaped FastAPI service exposing validated answers.

**Key decisions**

- **Tokenisation for coverage:** lowercase, NFC, punctuation stripped, stopwords removed, Snowball stemming (deterministic), with **numbers and units kept as atomic tokens** (`2 doses`, `70%`, `-20 °C`).
- **Confidence formula and gates:** as in ADR-002, with weights and floor in config.
- **Request limits:** question length 3–1000 characters, `top_k` 1–20 (default 5), with rate limiting via `slowapi` in-process (Redis later).
- **Sync or async:** retrieval is CPU-bound and fast, so route handlers are `async` and the pipeline runs via `run_in_threadpool`. Database writes are async and non-blocking.

**Deliverables checklist**

- [ ] `validation/coverage.py`, `numeric.py`, `confidence.py`, each with property-based tests (Hypothesis): coverage stays in [0, 1], is monotonic, and handles empty answers
- [ ] `services/qa_service.py` orchestrating retrieve → floor → generate → validate → status → log
- [ ] `api/routes/qa.py` (`/api/v1/qa` plus the `/qa` alias), thin handlers only
- [ ] Response model:

  ```json
  {
    "answer": "Health workers should perform hand hygiene before donning gloves [1] ...",
    "citations": [{"id": 1, "doc_id": "who-ipc-004", "title": "...", "source_org": "WHO",
                   "section_path": "PPE › Gloves", "chunk_id": "...", "snippet": "...", "score": 0.82}],
    "confidence": 0.78,
    "status": "validated",
    "meta": {"request_id": "...", "index_version": "a1b2c3d", "latency_ms": 41,
             "abstained": false, "signals": {"coverage": 1.0, "query_support": 0.71,
             "retrieval_score": 0.64, "numeric_ok": true}}
  }
  ```

- [ ] `health.py`: `/healthz` (liveness), `/readyz` (index loaded and DB reachable), `/version`
- [ ] `core/`: pydantic-settings config, structlog JSON logs with `request_id` middleware, Prometheus `/metrics` (`qa_requests_total{status}`, `qa_confidence` histogram, `qa_latency_seconds`, `qa_abstentions_total`), problem+json error handlers, CORS allow-list, security headers
- [ ] Lifespan: load and verify the index manifest at startup (fail fast if hashes do not match)
- [ ] API tests (httpx `AsyncClient`): happy path, abstention path, validation errors (422), bounds, alias parity
- [ ] OpenAPI snapshot test, so the contract cannot drift silently

**Exit criteria:** `curl` against `/qa` returns schema-valid JSON for both answerable and unanswerable questions, and p95 latency is under 150 ms locally.

---

### Phase 4 — Evaluation & Threshold Tuning · *M* (spec Phase 3) → 🏁 **Milestone M1: all success criteria met**

**Objective:** demonstrate SC2 and SC3 with defensible, reproducible evidence.

**Key decisions**

- **Gold set:** about 80–120 questions, split roughly as 65% direct, 20% paraphrased or acronym-heavy, and 15% **unanswerable or out-of-scope** (to test abstention). Use a stratified dev/test split of about 50/50 by topic.
- **Pass-rate denominator:** SC3 is measured on the **answerable** test questions. Abstention quality on unanswerable questions is reported separately: abstention recall (the share of unanswerable questions correctly marked `needs_review`) and the false-validation rate.
- **Threshold policy:** sweep 0.30–0.90 in steps of 0.05 on dev. Choose the threshold that maximises pass rate subject to a false-validation rate of at most 5% on unanswerables. **Keep 0.6 as the default unless the data justifies a change, and document the reason either way.**

**Deliverables checklist**

- [ ] `datasets/gold_dev.jsonl`, `gold_test.jsonl` and `DATASET_CARD.md` (annotation guide, relevance definition from ADR-001)
- [ ] `eval_retrieval.py`: P@1/3/5/10, Recall@K, MRR, nDCG@5, Hit@5, with per-topic breakdown and bootstrap 95% confidence intervals
- [ ] `eval_validation.py`: pass rate at the threshold, mean and median confidence, confidence histogram, abstention recall, false-validation rate
- [ ] `threshold_sweep.py`: pass rate and false-validation curves versus threshold (PNG and JSON)
- [ ] **Ablation table:** BM25 only, dense only, hybrid RRF, hybrid plus query expansion; hashing versus SVD embedder
- [ ] `reports/<run_id>/`: `metrics.json`, `per_query.csv`, **`low_confidence.csv`** (analyst review list), plots
- [ ] Eval runs written to the `eval_runs` table (prepared for the admin dashboard in Phase 5)
- [ ] `docs/evaluation-report.md`: method, results, contradictions, limitations, recommended threshold
- [ ] **CI quality gate:** the build fails if test-split P@5 < 0.65 or pass rate < 0.80

**Exit criteria:** SC1–SC4 all green in CI, with the report committed.

---

### Phase 5 — Persistence, Auth & Admin APIs · *M–L*

**Objective:** the backend features the admin dashboard needs.

**Key decisions**

- **Data model:** `users`, `query_log` (redacted question, status, confidence, signals, citations, latency, index_version, user_id), `reviews` (query_id, reviewer, verdict ∈ {approve, reject, correct}, note, corrected_citations), `eval_runs`, `index_versions` (version, manifest, created_at, active flag), `audit_log`, `app_config` (runtime threshold and weights, versioned).
- **Runtime-tunable threshold:** an admin can change it. The change is audit-logged, and pods pick it up by polling the config version every 30 s. Alternatively the threshold can stay environment-only and immutable. **Recommendation: runtime-tunable with audit**, because it shows operational maturity.
- **Feedback loop:** a reviewer's "correct" verdict can **promote the item into the gold dev set** (exported as JSONL). This closes the evaluation loop, which strengthens the project considerably.
- **Index rebuild from the admin UI:** in compose/dev it runs as a background job to a shared volume. In prod, rebuilds happen through CI/GitOps, and the admin UI only **lists and activates** published versions.

**Deliverables checklist**

- [ ] SQLAlchemy models, repositories and Alembic migrations, with `scripts/db-migrate.*` and `scripts/seed.*` (admin user and demo data)
- [ ] Auth: `/api/v1/auth/login`, `/refresh`, `/me`; Argon2 password hashing; JWT; RBAC dependency `require_role(...)`
- [ ] Admin routes (all paginated, filterable and sortable):
  - [ ] `GET /admin/stats?from&to` (volume, pass rate, mean confidence, abstention rate, p50/p95 latency, top topics, trend series)
  - [ ] `GET /admin/queries`, `GET /admin/queries/{id}`
  - [ ] `GET /admin/reviews?status=pending`, `POST /admin/reviews/{query_id}`
  - [ ] `GET /admin/eval-runs`, `POST /admin/eval-runs` (async trigger), `GET /admin/eval-runs/{id}`
  - [ ] `GET /admin/index/versions`, `POST /admin/index/versions/{v}/activate`, `POST /admin/index/rebuild` (dev only)
  - [ ] `GET /admin/documents` (corpus inventory with chunk counts)
  - [ ] `GET/PUT /admin/config` (threshold and weights, audited)
  - [ ] `GET /admin/audit-log`
- [ ] PHI-redaction hook and retention purge job
- [ ] Integration tests against Postgres via Testcontainers, plus RBAC matrix tests (each role × endpoint)

**Exit criteria:** every admin endpoint is covered by tests, and the RBAC matrix is green.

---

### Phase 6 — React Frontend: Query Assistant & Admin Dashboard · *L*

**Objective:** a polished, accessible, production-grade SPA.

**Key decisions**

- **Stack:** React + TypeScript + Vite, React Router, **TanStack Query** for server state, Zod for runtime validation, Tailwind + shadcn/ui (Radix primitives give accessibility by default), Recharts for charts, React Hook Form.
- **API client:** **generated from OpenAPI** (`openapi-typescript` plus a thin fetch wrapper) so the frontend cannot drift from the backend contract.
- **Auth storage:** access token kept in memory, refresh token in an httpOnly cookie (preferred), rather than localStorage (simpler but exposed to XSS).
- **Streamlit:** the spec marks it optional. **The React UI supersedes it, and this is stated explicitly in the README.**

**Deliverables checklist — Query Assistant**

- [ ] Question input with `top_k` control, keyboard submit, and loading, error and empty states
- [ ] Answer card: **status badge** (validated or needs-review), **confidence meter** with a signal breakdown tooltip, inline `[n]` citation chips
- [ ] **Evidence panel:** clicking a citation shows the source chunk with **overlapping tokens highlighted** and numbers checked, so the user can see exactly why the answer was validated
- [ ] Abstention UX: clear message, candidate sources shown, an "escalate for review" action
- [ ] Session query history in the sidebar, copy answer with citations, persistent clinical disclaimer banner

**Deliverables checklist — Admin Dashboard (reviewer and admin roles)**

- [ ] **Overview:** KPI tiles (queries, pass rate, mean confidence, abstention rate, p95 latency), trend charts, confidence distribution, top topics
- [ ] **Review Queue:** pending `needs_review` items, side-by-side question, candidate answer and evidence, approve, reject or correct, promote to the gold set
- [ ] **Query Explorer:** filters (status, confidence range, date, index version), detail drawer
- [ ] **Evaluation:** run history, P@K and pass-rate trend, threshold sweep chart, low-confidence list, "run evaluation" button
- [ ] **Index & Corpus:** versions with manifest hashes, activate a version, document inventory, rebuild (dev)
- [ ] **Settings:** threshold and weights editor showing the impact preview from the last sweep, audited
- [ ] **Audit Log:** filterable table
- [ ] Route guards by role, 403 page, responsive layout, dark mode
- [ ] Accessibility: WCAG 2.2 AA, keyboard navigation, axe checks in tests
- [ ] Vitest + React Testing Library + MSW tests for key components and hooks; stable `data-testid` attributes for Playwright

**Exit criteria:** all screens work against the real API, axe reports no serious violations, and Lighthouse accessibility scores 95 or higher.

---

### Phase 7 — Test Hardening & Quality Gates · *M*

**Objective:** consolidate the test pyramid and enforce it in CI (detail in §6).

**Key decisions**

- Coverage targets: domain (`rag/`) ≥ 90%, services ≥ 85%, overall backend ≥ 80%, frontend ≥ 70%.
- Contract testing: **Schemathesis** fuzzing of the OpenAPI spec.
- Load tool: **k6** or Locust. Recommendation: k6, because scripts are small and it fits CI.

**Deliverables checklist**

- [ ] Backend: unit, integration (Testcontainers Postgres), API, contract (Schemathesis), property-based (Hypothesis)
- [ ] Evaluation regression tests (the SC2/SC3 gates from Phase 4)
- [ ] Frontend: Vitest unit and component tests, MSW-mocked API
- [ ] **Playwright functional E2E** (`e2e/tests/`): ask → validated; ask → abstain; citation evidence panel; login per role; review approve flow; config change appears in the audit log; RBAC denial
- [ ] Load test: 50 virtual users for 5 minutes against `/qa`, with p95 < 300 ms and 0% 5xx (`scripts/load-test.*`)
- [ ] Security: `pip-audit`, `npm audit`, Bandit, Trivy (filesystem and image), Gitleaks
- [ ] `scripts/test.*` with flags `--backend --frontend --e2e --all --coverage`

**Exit criteria:** CI is green with every gate enforced.

---

### Phase 8 — Containerization (Docker & Compose) · *M*

**Key decisions**

- **Base images:** `python:3.12-slim` with a multi-stage `uv` build, or distroless. Recommendation: slim first, because it is easier to debug, with distroless noted as hardening.
- **Web serving:** an `nginx-unprivileged` image serves the static build and reverse-proxies `/api` to the API. This gives same-origin requests, so CORS can be avoided in deployment.
- **Index in images:** a separate `index.Dockerfile` builds the index artifact image from the corpus (ADR-008). Compose mounts it via a one-shot `indexer` service that writes to a named volume.

**Deliverables checklist**

- [ ] `api.Dockerfile`: multi-stage, non-root UID, `HEALTHCHECK`, no secrets, `.dockerignore`, deterministic `uv sync --frozen`
- [ ] `web.Dockerfile`: Node build stage → nginx-unprivileged; SPA fallback; gzip; cache headers; security headers including CSP
- [ ] `index.Dockerfile`: runs `pipeline.py build` and prints the manifest hash, which must match the CI determinism hash
- [ ] `docker-compose.yml`: `postgres` (healthcheck, volume), `migrate` (one-shot), `indexer` (one-shot), `api` (depends on the healthy and completed services), `web`
- [ ] `docker-compose.observability.yml` profile: Prometheus and Grafana with a provisioned **RAG dashboard JSON**
- [ ] Scripts: `docker-up.*`, `docker-down.*`, `docker-rebuild.*`, `docker-logs.*`, `smoke.*`
- [ ] Image size budget (API under about 400 MB) and a clean Trivy scan (no criticals)

**Exit criteria:** on a clean machine, `scripts/docker-up.sh` brings up a working stack and smoke tests pass.

---

### Phase 9 — Kubernetes Deployment · *M–L*

**Key decisions**

- **Kustomize or Helm:** **Kustomize** (base plus overlays) is recommended. It is simpler, native to `kubectl`, and the project has few variables to parametrise. Helm is the better fit if the chart will be distributed.
- **Local cluster:** **kind** (images loaded with `kind load docker-image`) or k3d.
- **North-south traffic:** the community **ingress-nginx controller has been retired by Kubernetes SIG Network** (verify current status at implementation time). Prefer the **Gateway API** (for example Envoy Gateway), or Traefik as an Ingress fallback.
- **Database:** an in-cluster Postgres StatefulSet for the local overlay; a **managed Postgres** (RDS, Cloud SQL or Azure DB) referenced by Secret for the prod overlay.
- **Secrets:** plain Secrets locally; External Secrets Operator or Sealed Secrets for prod (documented, not necessarily built).

**Deliverables checklist**

- [ ] `base/`: Namespace; API Deployment (2 replicas, **init container copying the index image into an `emptyDir`**, startup, readiness and liveness probes, resource requests and limits, `runAsNonRoot`, `readOnlyRootFilesystem`, `seccompProfile: RuntimeDefault`); Service; web Deployment and Service; ConfigMap; Secret template; migration Job (Argo/Helm-hook style, or run before rollout)
- [ ] HPA (CPU 70%, 2–6 replicas), PodDisruptionBudget (minAvailable 1), NetworkPolicies (web → api → postgres only), ServiceAccount with no token automount
- [ ] Gateway API `Gateway` + `HTTPRoute` (or Ingress) routing `/` to web and `/api` to api
- [ ] `overlays/local/` (kind, in-cluster Postgres, NodePort/port-forward) and `overlays/prod/` (managed DB, TLS, larger resources)
- [ ] Optional ServiceMonitor for the Prometheus Operator
- [ ] Scripts: `k8s-up.*` (create kind cluster, build and load images, apply, wait for rollout), `k8s-down.*`, `k8s-status.*`, `k8s-port-forward.*`
- [ ] Rolling-update verification: zero failed requests during `kubectl rollout restart` under k6 load
- [ ] Index rollout and rollback: change the index image tag, roll out, and roll back with `kubectl rollout undo`

**Exit criteria:** `scripts/k8s-up.sh` brings up a working cluster from scratch, and the E2E suite passes against it.

---

### Phase 10 — CI/CD Pipeline · *S–M*

**Pipeline (GitHub Actions)**

```text
PR:    lint → typecheck → unit → integration → contract → determinism → eval-gate
       → frontend tests → build images → trivy → kind deploy → playwright e2e
main:  all of the above → push images (GHCR, tagged by git sha and index_version) → SBOM (Syft) → sign (Cosign, optional)
tag:   release notes → prod overlay manifests rendered as an artifact
```

**Deliverables checklist**

- [ ] `ci.yml` with dependency caching for `uv` and npm, using a matrix (Linux for all jobs; Windows for determinism plus unit tests to prove PowerShell parity)
- [ ] Evaluation report and Playwright HTML report uploaded as artifacts
- [ ] Branch protection requires all gates
- [ ] `release.yml` for image publish, SBOM and rendered manifests

**Exit criteria:** a PR cannot merge with a failing quality gate.

---

### Phase 11 — Playwright Demo Suite & Video · *M*

**Objective:** a narrated, repeatable demo video generated by code.

**Key decisions**

- **Kept separate from the functional E2E tests:** `e2e/playwright.config.ts` defines two projects. `e2e` makes assertions, runs fast and records video only on failure. `demo` runs slowly, records video always, at a 1920×1080 viewport and video size.
- **Narration:** an injected **caption overlay** (a small DOM banner added via `page.evaluate`) announces each step, so the video explains itself without a voice-over.
- **Determinism:** run against a freshly seeded stack (`scripts/seed.* --demo`) with a fixed index version, so every recording looks the same.
- **Format:** Playwright writes `.webm`; `ffmpeg` converts it to H.264 `.mp4` (`-preset veryfast`) for easy sharing.

**Storyboard (`e2e/demo/demo.spec.ts`)**

1. Landing page and synthetic-corpus disclaimer
2. PPE question → **validated** answer, confidence meter, citations
3. Click a citation → evidence panel with overlap highlighting and the numeric check
4. Vaccination cold-chain question → validated, with a multi-source citation
5. Out-of-scope or unsupported question → **needs_review** abstention
6. Log in as an admin → Overview KPIs
7. Review Queue → approve the abstained item and promote it to the gold set
8. Evaluation page → P@5 trend and threshold sweep, then run an evaluation
9. Index page → versions, manifest hash, activate
10. Settings → threshold change appears in the Audit Log

**Deliverables checklist**

- [ ] `playwright.config.ts` with `e2e` and `demo` projects
- [ ] `e2e/demo/captions.ts` helper (`showCaption(page, text, ms)`)
- [ ] `demo.spec.ts` built from `test.step` blocks with paced waits
- [ ] `scripts/demo-record.*`: seed → run the demo project → find the `.webm` → convert to `artifacts/demo/healthcare-rag-demo-<timestamp>.mp4`
- [ ] Optional: chapter markers file (`demo-chapters.txt`) and a GIF teaser

**Exit criteria:** a single script produces the MP4 from a cold start.

---

### Phase 12 — Documentation, Final Review & Submission · *S–M* (spec Phases 4–5)

**Deliverables checklist**

- [ ] **README.md:** purpose, disclaimer, architecture diagram, quick start (local, Docker, k8s), configuration table, script index, metrics snapshot
- [ ] **RUNBOOK.md:**
  - [ ] Deploy, upgrade, rollback (app and index separately)
  - [ ] **Swapping in a secure real guideline repository:** implement the `DocumentSource` protocol (gateway, S3/Blob, SharePoint), authentication via workload identity, document-level ACL metadata and **retrieval-time access filtering**, re-annotating the gold set, re-tuning the threshold, a validation sign-off checklist
  - [ ] Treating retrieved text as **data, not instructions** (prompt-injection posture, relevant if the LLM generator is enabled)
  - [ ] Operations: alerts (abstention spike, latency, readiness failures), log queries, PHI-redaction verification, retention
  - [ ] Scaling path: when to move from `IndexFlatIP` to IVF/HNSW or an external vector database
- [ ] `docs/architecture.md`, `docs/api.md` (with examples), finalised ADRs
- [ ] `docs/evaluation-report.md` (final numbers, confidence intervals, ablations, limitations)
- [ ] **`docs/technical-summary.md`** (2–3 pages for stakeholders: problem, approach, results against criteria, risks, next steps)
- [ ] Submission bundle: tagged release, images, evaluation logs, low-confidence list, demo MP4, Playwright report
- [ ] Final review checklist: fresh-clone test on Linux and Windows, all scripts working, no secrets in history, licence and third-party notices

**Exit criteria:** a reviewer can reproduce every metric and the demo from a fresh clone using only `scripts/`.

---

## 5. Scripts Catalogue (`scripts/`)

**Conventions**

- Every script exists as **`name.sh` (bash) and `name.ps1` (PowerShell 7+)** with matching flags.
- Bash scripts start with `set -euo pipefail`; PowerShell scripts set `$ErrorActionPreference = 'Stop'`.
- Shared helpers live in `scripts/lib/common.sh` and `scripts/lib/Common.psm1` (coloured logging, prerequisite checks, `.env` loading, repo-root detection).
- Every script supports `--help`, is **idempotent**, and returns a non-zero exit code on failure (CI-safe).

| Script | Purpose | Key flags |
| --- | --- | --- |
| `setup` | Check prerequisites (uv, node, docker, kubectl, kind, ffmpeg), create environments, install Playwright browsers, copy `.env` | `--skip-playwright`, `--ci` |
| `reset-env` | Remove `.venv`, `node_modules`, `artifacts/` and caches, then re-run setup | `--keep-db`, `--yes` |
| `build-index` | Run `pipeline.py build` and print the manifest | `--corpus`, `--out`, `--embedder hashing\|svd` |
| `verify-determinism` | Build twice in temporary directories and compare all hashes | `--runs N` |
| `dev` | Run the API (uvicorn reload) and web (Vite) together | `--api-only`, `--web-only` |
| `db-migrate` | Run Alembic upgrade or downgrade | `--revision` |
| `seed` | Create the admin user, demo query log and reviews | `--demo`, `--reset` |
| `test` | Run the chosen test layers | `--backend --frontend --e2e --all --coverage` |
| `eval` | Retrieval and validation evaluation plus threshold sweep, writing a report | `--split dev\|test`, `--threshold` |
| `load-test` | k6 against `/qa` | `--vus`, `--duration`, `--target` |
| `lint` / `format` | ruff, mypy, eslint, prettier, tsc | `--fix` |
| `gen-client` | Export OpenAPI and regenerate TS types | — |
| `docker-up` / `docker-down` / `docker-rebuild` / `docker-logs` | Compose lifecycle | `--observability`, `--volumes` |
| `k8s-up` / `k8s-down` / `k8s-status` / `k8s-port-forward` | kind cluster plus Kustomize lifecycle | `--overlay local\|prod`, `--recreate` |
| `e2e` | Playwright functional suite | `--headed`, `--target local\|docker\|k8s` |
| `demo-record` | Seed, record the demo, convert to MP4 | `--target`, `--keep-webm` |
| `smoke` | Hit `/healthz`, `/readyz` and a sample `/qa` | `--base-url` |
| `security-scan` | pip-audit, npm audit, bandit, trivy, gitleaks | `--images` |
| `clean` | Remove build outputs and reports | `--all` |

---

## 6. Testing Strategy

```text
                    ▲  Demo (Playwright, recorded)           — presentation, not a gate
                   ╱ ╲ E2E (Playwright)                      — critical user journeys × 3 targets
                  ╱   ╲ Load (k6) · Security scans           — performance and supply-chain gates
                 ╱     ╲ Contract (Schemathesis) · OpenAPI snapshot
                ╱       ╲ Evaluation gates (P@5, pass rate, false-validation rate)
               ╱         ╲ API (httpx) · Integration (Testcontainers Postgres, real index)
              ╱___________╲ Unit + property-based (pytest, Hypothesis, Vitest, RTL)
```

| Layer | Focus | Gate |
| --- | --- | --- |
| Unit | chunker, embedder determinism, fusion, coverage maths, numeric check, confidence, React components | coverage thresholds |
| Property-based | coverage ∈ [0, 1]; determinism is invariant to input order and `PYTHONHASHSEED` | must pass |
| Integration | index build → retrieval; repositories against real Postgres | must pass |
| API | status codes, schemas, bounds, RBAC matrix, problem+json | must pass |
| Contract | Schemathesis on all endpoints; OpenAPI diff | no breaking change |
| Evaluation | SC2 and SC3 on the test split; false-validation ≤ 5% | **build fails if missed** |
| E2E | assistant flows, admin flows, role guards | must pass on kind |
| Load | p95 < 300 ms, 0% 5xx at 50 virtual users | must pass on main |
| Security | no critical CVEs, no secrets | must pass |

---

## 7. Milestones & Critical Path

| Milestone | Phases | Outcome |
| --- | --- | --- |
| **M1 — Core criteria met** | 0 → 4 | SC1–SC4 green; evaluation report committed. **Protect this milestone above all others.** |
| **M2 — Product complete** | 5 → 7 | Admin APIs, React assistant and dashboard, full test pyramid |
| **M3 — Deployable** | 8 → 10 | Compose, kind/k8s, CI/CD with gates |
| **M4 — Submission** | 11 → 12 | Demo MP4, RUNBOOK, technical summary, release |

**Indicative total:** about 5–6 weeks for one engineer (M1 in about 2 weeks).

**If time runs short, cut in this order:** prod k8s overlay → observability profile → index rebuild from the admin UI → dark mode → SVD ablation. **Never cut:** evaluation rigour, abstention behaviour, the determinism check, or the RUNBOOK.

---

## 8. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R1 | P@5 target unreachable because of the relevance definition | High if ignored | High | ADR-001 section-level qrels with at least 3 relevant chunks per question |
| R2 | Coverage metric trivially about 1.0 for extractive answers, so pass rate is meaningless | High | High | ADR-002 composite confidence plus numeric gate; report false-validation rate |
| R3 | Threshold overfit to the evaluation data | Medium | Medium | Dev/test split; tune on dev only; bootstrap confidence intervals |
| R4 | Cross-platform non-determinism (CRLF, hash salt, BLAS) | Medium | High | `.gitattributes`, blake2b, float32, pinned versions, Windows CI job |
| R5 | Hashed embeddings weak on paraphrases | Medium | Medium | Hybrid BM25 + RRF, acronym expansion, paraphrase slice in the gold set |
| R6 | Scope creep (dashboard and k8s) delays core criteria | Medium | High | Vertical-slice ordering; M1 first; cut list in §7 |
| R7 | `faiss-cpu` wheel availability on a dev OS or architecture | Low–Medium | Medium | Verify early in Phase 0; Docker as fallback dev environment |
| R8 | Users treat output as clinical advice | Medium | High | Persistent disclaimer, abstention-first policy, synthetic labelling |
| R9 | PHI typed into questions ends up in logs | Medium | High | ADR-009 redaction, opt-out text logging, retention TTL |
| R10 | Flaky E2E or demo runs | Medium | Low | Seeded data, `data-testid` selectors, web-first assertions, retries in CI only |

---

## 9. "Above & Beyond" Backlog (optional, clearly out of core scope)

| Idea | Value | Effort |
| --- | --- | --- |
| **Evidence highlighting** of overlapping tokens in the UI | Makes validation visible and trustworthy | S (planned in Phase 6) |
| **Reviewer → gold-set feedback loop** | Continuous evaluation improvement | S (planned in Phase 5) |
| **Conflict detection:** flag when cited sources disagree (for example two guideline versions) | High clinical-safety value | M |
| **Version-aware retrieval:** prefer the latest `effective_date`, show "superseded" badges | Realistic guideline governance | S–M |
| Cross-encoder reranker behind a feature flag (offline model) | Better precision; kept outside the deterministic path | M |
| Optional LLM generator (Responses API) behind the same validator, with an A/B eval report | Shows extensibility without losing grounding | M |
| Semantic cache for repeated questions, keyed by `index_version` | Lower latency | S |
| OpenTelemetry traces with spans for retrieval, generation and validation, plus a Jaeger profile | Production observability | S |
| Per-topic calibration curves (reliability diagram) for confidence | Statistical rigour | S |

---
