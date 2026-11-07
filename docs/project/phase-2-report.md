# Phase 2 Report — Retrieval & Extractive QA Core

- **Date:** 2026-11-07 · **Plan ref:** `plan.md` §4 Phase 2 (brief Phase 2, part 1)
- **Result:** all deliverables built and verified. **Exit criterion met with margin:**
  the expected document is in the top 5 for **15/15** smoke questions (target ≥ 9/10).

## 1. Deliverables

| Plan item | Status | Where |
| --- | --- | --- |
| `domain/protocols.py`: Embedder, VectorStore, SparseIndex, **Retriever, Generator, Validator** | ✅ (Validator is implemented in Phase 3) | `backend/app/domain/protocols.py`, result types in `models.py` |
| `retrieval/hybrid.py`: RRF, `top_k` guard, deterministic order | ✅ `reciprocal_rank_fusion` is a pure function; ties break on `chunk_id` | `backend/app/rag/retrieval/` |
| Acronym and synonym query expansion (deterministic map) | ✅ 22 acronyms (both directions) + 14 synonym groups, versioned JSON | `retrieval/query_expansions.json`, `expansion.py` |
| `generation/extractive.py`: splitter, scorer, MMR, citation markers | ✅ plus answer-type cues and sentence character offsets | `backend/app/rag/generation/` |
| `IndexRegistry`: atomic in-memory swap | ✅ immutable `RagRuntime` snapshots; a failed load keeps the old index | `backend/app/rag/index/registry.py`, `rag/runtime.py` |
| LLM generator behind `Generator`, off by default | ✅ protocol only; `GENERATOR=llm` fails fast with a clear message | `rag/runtime.py` |
| Unit tests: fusion maths, tie-breaks, splitting, citation integrity | ✅ | `tests/unit/test_retrieval.py`, `test_extractive.py`, `test_registry.py` |
| Integration: fixture corpus → expected `doc_id` in the top 5 | ✅ plus the real-corpus smoke gate | `tests/integration/test_retrieval_smoke.py` |
| Developer CLI | ✅ `pipeline.py ask "question"` shows expansion, fused ranks and the answer | `backend/scripts/pipeline.py` |

## 2. Retrieval results (15-question smoke set)

`tests/fixtures/smoke_questions.json` covers acronyms (AIIR, PEP, CLABSI, AEFI), lay
paraphrases ("taking off PPE", "vaccine shot") and 15 of the topics. It is **not** the
gold set: no tuning was done against it.

| Mode | hit@5, no expansion | MRR | hit@5, with expansion | MRR |
| --- | --- | --- | --- | --- |
| Dense (hashed) only | 14/15 | 0.694 | 15/15 | 0.889 |
| BM25 only | 15/15 | 0.900 | 15/15 | **0.967** |
| **Hybrid RRF (default)** | 15/15 | 0.856 | **15/15** | **0.933** |

- Expansion improves every mode. It is what lets the dense retriever match "taking off" to "doffing".
- BM25 + expansion edges out hybrid on MRR on this small set. Hybrid stays the default
  because it is more robust under paraphrase and is the configuration the plan evaluates;
  **the final choice is made on the Phase 4 dev split** (ADR-0004).

## 3. Decisions and findings

| Topic | Decision | Why / evidence |
| --- | --- | --- |
| **Superseded guidance** | **ADR-0010:** never extract answer text from superseded documents; keep them retrievable | The fit-testing answer quoted the superseded "every two years". It now quotes the current "before first use and annually thereafter" (integration test) |
| Answer-type cues | Questions asking *how long / how often / what temperature / how many / when / what order* boost sentences containing a duration, frequency, °C, number, time condition or a list step | Without them, sentences repeating the question's nouns beat the sentences that actually answer it. Deterministic regexes in `answer_types.py` |
| Modal verbs | `must`, `shall`, `may`, `might` added to stop-words (analysis v2) | "must" matched every policy sentence and won selection on noise |
| Sentence spans | New `sentence_spans()` with offsets into the original chunk text; `split_sentences()` unchanged | The UI highlights the exact source text (Phase 6). The chunker is untouched, so chunking is identical; a test asserts both functions agree on every corpus paragraph |
| Candidate units | Sentences, whole list items (with continuation lines) and table data rows rendered as `cell: cell` | Procedures and tables carry many of the answers (steps, temperature tables) |
| Citation numbering | `[1..n]` in order of first use; each marker sits before the terminal punctuation | Checked against the API contract v1 model in a test |
| RRF score normalisation | `score / (n_retrievers / (k+1))` → (0, 1] | Feeds `retrieval_score` in the ADR-0002 confidence formula |
| Candidate depth | `RETRIEVAL_CANDIDATE_K = 50` per retriever | Deep enough that RRF can promote documents ranked well by only one retriever |
| `index_version` | `549fbb1ead30` → **`097a9ef4becf`** | Intended: analysis v2 and the `superseded` field on chunks. Rebuilds are byte-identical (3 seeds) |

### Known limitation (input to Phase 4)

**MMR can drop the best sentence when two candidates are near-duplicates.** For *"How long
should alcohol-based handrub be applied?"* the ideal sentence ("…rub until dry; the full
procedure takes 20–30 seconds") is ranked **first** with λ = 1.0. At the default λ = 0.7
it is penalised as redundant with the similar soap-and-water sentence ("…the full procedure
takes 40–60 seconds"), which is selected first. I tried and reverted a fix that inherited
context from the previous sentence: it did not solve this case and made another worse.
**Action for Phase 4:** tune `ANSWER_MMR_LAMBDA` and the scorer weights on the dev split.
Phase 3's validator still checks the answer against its evidence; this is answer
*selection* quality, not grounding.

## 4. Verification evidence

| Check | Result |
| --- | --- |
| Backend tests | **178 passed** (Phase 1: 130) |
| `ruff`, `ruff format`, `mypy --strict` | clean (65 source files) |
| Smoke gate (integration test) | hit@5 ≥ 0.9 enforced; currently 15/15 |
| Determinism | 3 isolated rebuilds byte-identical (`097a9ef4becf`) |
| Registry | concurrent readers during 5 swaps: no errors; failed load keeps the previous index |
| Contract | a generated answer validates against `QAResponse` v1 (markers ↔ citations) |

## 5. Your actions

```bash
scripts/setup.sh                                  # no new dependencies; re-syncs and runs all checks
scripts/build-index.sh --inspect                  # expect index_version 097a9ef4becf
cd backend && uv run python scripts/pipeline.py ask "How often is respirator fit testing required?"
cd .. && git add -A && git commit -m "feat(rag): phase 2 hybrid retrieval and extractive QA core"
git push
```

## 6. Hand-off to Phase 3

Phase 3 implements `Validator` (coverage, query support, numeric gate, confidence), the
`QAService` that maps `GeneratedAnswer` to contract v1, and the real `/qa` handler.
The registry and runtime are ready to be wired into the FastAPI lifespan.
