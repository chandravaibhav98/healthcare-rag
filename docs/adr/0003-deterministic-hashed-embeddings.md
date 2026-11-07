# ADR-0003 — Deterministic 256-D signed feature-hashing embedder

- **Status:** Accepted (implemented and verified in Phase 1, 2026-11-07)
- **Plan ref:** `plan.md` §3 ADR-003, §4 Phase 1 · **Affects:** SC1, SC2
- **Evidence:** [spike 2026-11-07](../spikes/2026-11-07-faiss-determinism.md) ·
  [Phase 1 report](../project/phase-1-report.md) · `backend/app/rag/embeddings.py`

## Context

The brief requires deterministic 256-D embeddings with no external API calls (D2) and
byte-identical rebuilds (SC1). Semantic quality still matters for SC2.

## Options considered

| Option | Deterministic | Corpus-independent | Quality | Notes |
| --- | --- | --- | --- | --- |
| **A. Signed feature hashing** | ✅ incl. cross-OS (see below) | ✅ except IDF | Lexical plus subword | Chosen |
| B. TF-IDF → TruncatedSVD(256) | ⚠️ LAPACK/BLAS variance | ❌ refit per corpus | Some semantics (LSA) | Deferred to the Phase 4 ablation |
| C. Local sentence-transformer → 256-D | ⚠️ float variance; model download | ✅ | Best | Conflicts with "no external dependency" |

## Decision

`HashingEmbedder` (embedder version 2):

| Aspect | Rule |
| --- | --- |
| Features | Word unigrams, word bigrams and char 3–5-grams (with `<w>` boundaries), all over **non-stop-words**; numbers are atomic and get no char-grams |
| Weights | word 1.0 · bigram 0.7 · char 0.35 (untuned defaults; tuned on dev in Phase 4) |
| Term weighting | `(1 + ln tf) × (ln((1+N)/(1+df)) + 1)`, smoothed IDF; unseen query features get the maximum IDF |
| Hashing | `blake2b(key=EMBEDDING_HASH_SALT, digest_size=8)`; bucket = `h mod dim`, sign = top bit. **Never** Python `hash()` |
| Input text | `title \n section path \n chunk text` (a contextual header) |
| Output | L2-normalised `float32`, `dim = 256` |
| Learned state | Integer document frequencies only (`embedder.json`), so the state has no float serialisation ambiguity |

### Cross-platform determinism rules (SC1)

1. Features are accumulated in **sorted order** with Python floats (IEEE-754 binary64,
   fixed operation order).
2. `ln` uses `decimal.Decimal.ln` (`analysis.exact_ln`), which is **correctly rounded in
   software**. `math.log` was rejected because glibc and the MSVC CRT may differ by one
   ulp, which can flip a `float32` rounding and break cross-OS byte identity.
3. The norm uses `math.fsum` and `math.sqrt` (exactly specified), not BLAS.
4. Corpus text is canonicalised (NFC, LF, trailing spaces stripped) before hashing, so
   a CRLF checkout yields the same `index_version`.

## Consequences

- **Positive:** reproducible across processes, hash seeds and checkouts (all verified),
  fast (42 documents in about 1 s), no model download, explainable.
- **Negative:** dense retrieval alone is weak on paraphrases (risk R5). On an informal
  10-question probe, dense P@5 was about 0.38, while BM25 found the expected section in
  its top 4 for all 10 questions. Hybrid retrieval (ADR-0004) is therefore required, not
  optional. Removing stop-words improved the probe from 0.34 to 0.38. Weight tuning is
  deliberately deferred to the Phase 4 dev split to avoid overfitting.
- **Deferred:** the `SvdEmbedder` ablation moves from Phase 1 to Phase 4, where it is
  actually used (the plan's §7 cut list allows cutting it entirely).

## Verification

- `tests/unit/test_embeddings.py`: byte-identical vectors, state round-trip, unchanged
  output under 4 different `PYTHONHASHSEED` values in separate processes.
- `tests/integration/test_index_build.py`: byte-identical builds; CRLF corpus gives the
  same index.
- CI `determinism` + `determinism-cross-os`: 3 isolated rebuilds per OS, then a
  byte-for-byte comparison of the Linux and Windows manifests.
