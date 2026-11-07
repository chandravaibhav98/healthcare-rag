# ADR-0003 — Deterministic 256-D signed feature-hashing embedder

- **Status:** Proposed (draft; finalised at the start of Phase 1)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-003, §4 Phase 1 · **Affects:** SC1, SC2
- **Evidence:** [spike 2026-11-07](../spikes/2026-11-07-faiss-determinism.md)

## Context

The brief requires deterministic 256-D embeddings with no external API calls (D2, SC1:
byte-identical rebuilds). Semantic quality still matters for SC2.

## Options considered

| Option | Deterministic | Corpus-independent | Quality | Notes |
| --- | --- | --- | --- | --- |
| **A. Signed feature hashing** (word 1–2-grams + char 3–5-grams → 256-D, sublinear TF × IDF, L2) | ✅ | ✅ (except IDF) | Lexical plus subword | Spike: rebuilds identical across `PYTHONHASHSEED`; char n-grams fixed top-1 from 2/3 to 3/3 |
| B. TF-IDF → TruncatedSVD(256, fixed seed) | ⚠️ BLAS/solver variance | ❌ refit per corpus | Some semantics (LSA) | Kept as an ablation baseline |
| C. Local sentence-transformer → 256-D projection | ⚠️ float variance; model download | ✅ | Best semantics | Conflicts with the spirit of "no external dependency" |

## Decision (proposed)

Use **A** as the production embedder behind an `Embedder` protocol, with B implemented as
an ablation. Determinism rules:

- hash with `hashlib.blake2b(key=EMBEDDING_HASH_SALT)`, **never** Python `hash()`;
- `float32` throughout; inputs sorted by path; text normalised to NFC with LF line endings;
- IDF computed over the committed corpus only and stored in the manifest;
- `EMBEDDING_DIM`, the salt, the tokeniser config, and the faiss/numpy/Python versions
  are hashed into `index_version`.

## Consequences

- **Positive:** reproducible, fast, no model download, easy to explain.
- **Negative:** weak on true paraphrases (risk R5). Mitigated by hybrid BM25 retrieval
  and acronym expansion (ADR-0004), and measured by the paraphrase slice of the gold set.

## Verification

Phase 1 unit tests (byte-identical vectors, invariance to `PYTHONHASHSEED`) and the CI
`determinism` job on Linux **and** Windows.
