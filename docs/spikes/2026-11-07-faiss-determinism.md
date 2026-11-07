# Spike 2026-11-07 — Deterministic hashed embeddings + FAISS

- **Purpose:** test risks R4 (cross-platform non-determinism), R5 (hashed vectors are
  lexically weak) and R7 (`faiss-cpu` wheel availability) before Phase 0 drafts
  ADR-003 and ADR-005.
- **Code:** [`faiss_determinism_spike.py`](faiss_determinism_spike.py). This is
  throwaway code, not the production embedder.
- **Feeds:** ADR-0003, ADR-0005, risk register §8.

## Environment

| Item | Value |
| --- | --- |
| OS | Linux x86_64 (Ubuntu 22.04 VM) |
| Python | 3.12.15 (provisioned by `uv`) |
| faiss-cpu | 1.15.1 |
| numpy | 2.5.4 |

## Method

1. Embed 4 synthetic guideline sentences into 256-D float32 vectors using
   **blake2b-keyed signed feature hashing**, then L2-normalise them.
2. Build `faiss.IndexFlatIP` twice and compare the SHA-256 of `faiss.serialize_index`.
3. Repeat the whole process in separate processes with different `PYTHONHASHSEED` values.
4. Run 3 queries and check whether the expected document ranks first (top-1), using
   two tokenisers: words only, and words plus char 3–5-grams.

## Results

| Tokeniser | Rebuild byte-identical | Identical across `PYTHONHASHSEED` (default, 4242) | Top-1 correct |
| --- | --- | --- | --- |
| words | ✅ `78b76c65…` | ✅ | 2 / 3 |
| words + char 3–5-grams | ✅ `34f78578…` | ✅ | **3 / 3** |

Additional facts:

- `faiss-cpu` 1.15.1 (released 2026-09-16) publishes a `cp312-win_amd64` wheel on PyPI,
  so **R7 is low risk for Windows development**. Docker remains the fallback.
- The original `Plan.md` on the developer machine was saved with **CRLF** line endings.
  This confirms R4 is a real risk, not a theoretical one: corpus files authored on the
  same machine would hash differently from a Linux checkout unless `.gitattributes`
  enforces LF.

## Conclusions

1. **SC1 is achievable** with blake2b hashing + float32 + `IndexFlatIP` on a single
   platform. Determinism **across Linux and Windows** is still unproven. The Phase 1
   CI job `determinism` must run on both OSes, as `plan.md` Phase 10 already requires.
2. **R5 is confirmed.** Word-only hashing missed `vaccine storage` → `store vaccines`.
   Subword (char n-gram) features fixed it in this small sample. This supports the
   ADR-003 recommendation (word uni/bigrams **and** char 3–5-grams) and the hybrid
   BM25 retrieval in ADR-004.
3. The sample is tiny (4 documents, 3 queries). These results are **evidence of
   feasibility, not evidence of quality**. Retrieval quality is measured only by the
   Phase 4 gold set.

## Follow-ups

- [ ] Phase 0: cite this spike in ADR-0003 and ADR-0005.
- [ ] Phase 1: re-run the determinism check on Windows (`pwsh` + native Python) and
      record the result here.
