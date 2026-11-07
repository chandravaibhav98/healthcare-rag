# Phase 1 Report — Synthetic Corpus & Deterministic Indexing

- **Date:** 2026-11-07 · **Plan ref:** `plan.md` §4 Phase 1 (brief Phase 1)
- **Result:** all deliverables built and verified locally. **SC1 is met on Linux.** The
  cross-OS half of SC1 (Linux vs Windows) is wired into CI and confirmed by the first
  run on GitHub.

## 1. Deliverables

| Plan item | Status | Where |
| --- | --- | --- |
| Corpus (40–60 docs) + `CORPUS_CARD.md` | ✅ 42 docs, 15 topics, 3 conflict pairs | `corpus/`, [`corpus/CORPUS_CARD.md`](../../corpus/CORPUS_CARD.md) |
| `ingestion/loader.py`: front-matter validation, sorted traversal, NFC/LF | ✅ plus file-name/org/supersession checks | `backend/app/rag/ingestion/` |
| `ingestion/chunker.py`: heading-aware, list/table-safe, overlap | ✅ | `chunker.py`, `sentences.py`, `normalizer.py` |
| `rag/embeddings.py`: `HashingEmbedder(256)` | ✅ (ADR-0003 Accepted) | `backend/app/rag/embeddings.py` |
| `SvdEmbedder` ablation | ⏭️ **Moved to Phase 4** (where it is used; plan §7 allows cutting it) | — |
| `index/faiss_store.py`, `index/bm25_store.py`, deterministic ties | ✅ BM25 persisted as **JSON**, not pickle (§3) | `backend/app/rag/index/` |
| `index/manifest.py` (hashes, versions, `index_version`) | ✅ | `manifest.py` |
| `backend/scripts/pipeline.py`: `build`, `verify`, `inspect` | ✅ plus `determinism` | `backend/scripts/pipeline.py` |
| `scripts/build-index.*`, `scripts/verify-determinism.*` | ✅ `.sh` + `.ps1` | `scripts/` |
| Unit tests (chunker, embedder determinism incl. `PYTHONHASHSEED`, manifest) | ✅ | `backend/tests/unit/`, `backend/tests/integration/` |
| CI `determinism` job | ✅ 3 rebuilds per OS on Linux + Windows, then a **byte-for-byte comparison of the two manifests** | `.github/workflows/ci.yml` |

**Exit criteria**

| Criterion | Status |
| --- | --- |
| SC1 passes in CI | ✅ Locally: 3 isolated builds byte-identical; CRLF corpus gives the same index; bash and PowerShell builds identical. ⏳ Cross-OS job confirmed on the first GitHub run |
| `pipeline.py inspect` shows sensible chunks for every document | ✅ §2 |

## 2. Index statistics (`scripts/build-index.sh --inspect`)

```text
index_version 549fbb1ead30  ·  42 documents  ·  209 chunks
tokens/chunk  min 23  p10 43  median 72  p90 100  max 153  (target 80–160)
outliers      19 below 40 tokens · 0 above 160
chunks/doc    min 4  max 6
by org        CDC 70  NIH 69  WHO 70
```

The 19 short chunks are complete closing sections ("Records", "Monitoring",
"Confidentiality"), not fragments, so keeping them whole is correct. Only 1 of 208
sections needed splitting, so in practice a chunk is a section, which suits section-level
relevance (ADR-0001).

## 3. Decisions and deviations

| Topic | Decision | Why |
| --- | --- | --- |
| **Chunk size** | Default **80–160** tokens (plan: 180–350). Configurable via `CHUNK_*` | Guideline H2 sections are 25–170 tokens and H2 is a hard boundary, so the plan's minimum was unreachable. Measured, not guessed (§2) |
| Cross-OS float determinism | `ln` via `decimal` (correctly rounded); `fsum`/`sqrt` for the norm; sorted accumulation | `math.log` may differ by one ulp between glibc and MSVC → different `float32` bytes on Windows |
| Canonical text | NFC + LF + trailing-space strip **in memory** before hashing | `index_version` does not depend on how a file was checked out |
| Manifest | No timestamps, paths or hosts; Python **minor** version only | Two correct machines must produce byte-identical manifests |
| BM25 persistence | `bm25.json` instead of the plan's `bm25.pkl` | Unpickling executes code (security); JSON is byte-stable |
| Stop-words | Excluded from embedder features (embedder v2) | Principled noise reduction; 10-question probe P@5 0.34 → 0.38. Weights are **not** tuned yet (Phase 4 dev split) |
| Chunk IDs | `doc::section-slug::NNNN`, ordinal **per section** | Adding text to one section does not renumber the chunks (or gold labels) of other sections |
| Contextual header | Embedded text = title + section path + body | Short sections still match questions about their topic |
| SVD ablation | Deferred to Phase 4 | Only Phase 4 uses it; it can never be byte-identical across OSes anyway |
| Dependencies | `faiss-cpu 1.15.1`, `numpy 2.5.4`, `pyyaml 6.0.3` (`safe_load` only), `snowballstemmer 3.1.1` | Exact pins + `uv.lock` |
| Git Bash | `PYTHONUTF8=1` exported by the script libraries | Python under mintty otherwise crashes printing `›`, `—` or `°C` ([working agreements](working-agreements.md)) |

## 4. Early retrieval signal (input to Phase 2)

An informal probe with 10 realistic questions (not a gold set; no tuning was done on it):

- **BM25** placed an expected section in its top 4 for **10/10** questions.
- **Dense (hashed)** was noisier (P@5 ≈ 0.38), e.g. *"order for removing PPE"* did not
  match "doffing".

This confirms that hybrid retrieval (ADR-0004) is required and gives Phase 2 a concrete
target: RRF fusion must not drag BM25's good results down. It also suggests a deterministic
synonym map (`removing ↔ doffing`, `putting on ↔ donning`) next to the acronym map.

## 5. Verification evidence

Clean clone in the Linux VM (Python 3.12, Node 26), plus PowerShell 7.4:

| Check | Result |
| --- | --- |
| Backend tests | **130 passed** (Phase 0: 60) |
| `ruff` / `ruff format` / `mypy --strict` | clean (53 source files) |
| `pipeline.py determinism --runs 3` | 5/5 artifacts byte-identical across 3 processes with different hash seeds |
| CRLF copy of the corpus | identical index (integration test) |
| `build-index.sh` vs `build-index.ps1` | identical `manifest.json` |
| Tampering / staleness | detected by `verify` and refused by `load_index` (fail fast) |
| `actionlint` (updated `ci.yml`) | 0 findings |
| Corpus guards | 42 docs, 3 orgs × 12 core topics, LF/UTF-8, every doc ≥ 3 chunks |

## 6. Your actions

```bash
# In Git Bash, from the repo root
git mv -f Plan.md plan.md            # still outstanding from Phase 0
scripts/setup.sh                     # installs faiss-cpu, numpy, pyyaml, snowballstemmer
scripts/build-index.sh --inspect     # should print index_version 549fbb1ead30 (§2)
scripts/verify-determinism.sh        # PASS on Windows too
git add -A
git update-index --chmod=+x scripts/build-index.sh scripts/verify-determinism.sh
git commit -m "feat(rag): phase 1 synthetic corpus and deterministic index pipeline"
git push                             # watch the determinism-cross-os job
```

If your Windows build prints a **different** `index_version` from the one above, stop and
report it: that would be a real SC1 cross-OS finding. The CI job checks the same thing.

## 7. Hand-off to Phase 2

The index loads with full integrity checks (`load_index`), and both retrievers work.
Phase 2 adds RRF fusion with `chunk_id` tie-breaks, acronym and synonym expansion
(§4), and the extractive generator. The sentence splitter it needs already exists
(`ingestion/sentences.py`) and is tested.
