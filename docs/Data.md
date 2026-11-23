> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Data

The guideline corpus, the index built from it, and the gold evaluation sets. Everything
here is **synthetic**.

## 1. Corpus (`corpus/`)

- 72 markdown documents in `who/`, `nih/` and `cdc/`, written in the style of those
  organisations. Topics: infection prevention and control, hand hygiene, PPE,
  respiratory precautions, sterilisation, sharps, vaccination, cold chain, adverse events,
  outbreak response, waste.
- Deliberate near-duplicates and superseded versions test citation and version handling
  (ADR-0010).
- Each file has YAML front-matter: `doc_id, title, source_org, version, effective_date,
  topic[], audience, jurisdiction, synthetic: true`.
- Line endings are forced to LF by `.gitattributes`; this is required for determinism.

Card: [`corpus/CORPUS_CARD.md`](../corpus/CORPUS_CARD.md).

## 2. Index artifacts

`scripts/build-index.sh` writes to `artifacts/index/` (`INDEX_DIR`):

| File | Contents |
| --- | --- |
| `index.faiss` | `IndexFlatIP` over 256-D float32 L2-normalised hashed vectors |
| BM25 store | Term statistics for lexical ranking |
| `chunks.jsonl` | Chunk text, `chunk_id` (`doc_id::section_slug::ordinal`), section path, hashes |
| `manifest.json` | Corpus hash, per-file hashes, config hash, library versions, artifact SHA-256s, `index_version` |

`index_version` is a short hash of the corpus and the index configuration, so any change
to either produces a new version. The API verifies the manifest at start-up and refuses
a corrupted index. Published versions are kept under `INDEX_STORE_DIR` and can be
activated or rolled back from the admin UI.

## 3. Gold evaluation sets (`backend/evaluation/datasets/`)

| | Dev pool | Held-out test-v2 |
| --- | --- | --- |
| Questions | 144 | 95 |
| Answerable | 122 | 83 |
| Unanswerable | 22 | 12 |

- Edit the YAML sources (`gold_source.yaml`; `gold_test_source.yaml` only before first
  use), then run `uv run python -m evaluation.build_gold`. The JSONL files, manifest and
  JSON Schema are generated; CI checks they are current.
- Relevance is judged at section level (ADR-0001).
- Thresholds and weights are tuned on dev only and reported on test.
- Reviewers can promote corrected items into the dev pool from the review queue.

Card: [`DATASET_CARD.md`](../backend/evaluation/datasets/DATASET_CARD.md). Results:
[evaluation report](evaluation-report.md).

## 4. Data handling

Questions typed by users may contain patient information even though the corpus is
synthetic. They are redacted before storage, raw-text logging is off in production, and
the query log has a retention period (ADR-0009, [Database.md](Database.md)).

## 5. Replacing the corpus

To point the system at a real, secure guideline repository, follow
[RUNBOOK §4](../RUNBOOK.md): implement `DocumentSource`, snapshot before building, add
access-control metadata and retrieval-time filtering, re-annotate the gold set and
re-tune the threshold.
