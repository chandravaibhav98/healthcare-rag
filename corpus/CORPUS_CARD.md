# Corpus Card — Synthetic Guideline Corpus v2

> ⚠️ **Every document in this folder is synthetic.** The texts are written in the *style*
> of WHO, CDC and NIH infection-prevention guidance for software development and
> evaluation only. They are **not** issued by, endorsed by or copied from those
> organisations, and they are **not clinical guidance**. Numbers are plausible but
> must not be used for patient care.

## 1. Provenance

| Item | Value |
| --- | --- |
| Authoring | LLM-assisted drafting (project readiness Q6), reviewed and frozen on 2026-11-07 |
| Real source text | None copied. Wording is original. Facts reflect widely published IPC concepts at a general level |
| Change policy | Frozen. Never regenerated at build time (SC1). Edits are deliberate commits and change `index_version` |
| v2 (2026-11-12, Phase 4) | 30 documents added: WHO pocket guides, CDC quick references and NIH ward procedures (§2a) |
| Licence | Same as the repository |

## 2. Shape

| Measure | Value |
| --- | --- |
| Documents | 72 (WHO 25 · CDC 25 · NIH 22); v1 had 42 |
| Topics | 15 (all 15 now covered by all three organisations) |
| Superseded/current pairs | 3 (deliberate conflicts, §5) |
| Chunks (default config 80–160 tokens) | 346 (v1: 209); `index_version` 6ce73ffaf982 |
| Build | `scripts/build-index.sh --inspect` · `index_version` is printed and stored in `manifest.json` |

## 2a. Why v2 exists, and its risk

Precision@5 can only reach 0.65 if questions have, on average, more than 3.25 relevant
chunks (ADR-0001). With honest labels, v1 gave 2.7 per question and capped P@5 at 0.54
for a perfect retriever. Real guideline repositories repeat core guidance across many
documents (full guideline, pocket guide, quick-reference card, local ward procedure),
so v2 adds that layer: 30 documents, mostly 4–5 short sections each, that restate each
topic's core guidance with the same values as the parent organisation's main document.
They are written as procedures and summaries, never as question-and-answer FAQs, which
would make retrieval artificially easy.

**Risk, stated plainly:** v2 was written after the v1 gold questions existed, by the same
person, so the new documents could favour those questions. Mitigations: the documents
cover each topic's guidance broadly rather than the questions; the labels were extended
by reading every new chunk with the unchanged grading guide; the final claims rest on a
second test set (test-v2) written *after* v2 and before any further tuning
(`backend/evaluation/datasets/DATASET_CARD.md`).

## 3. File conventions (enforced by `backend/app/rag/ingestion/loader.py`)

- Path: `corpus/<org>/<doc_id>.md`, where `<org>` ∈ {`who`, `cdc`, `nih`} matches `source_org`.
- `doc_id`: `<org>-<topic-code>-<nnn>`, e.g. `who-hh-001`.
- UTF-8, LF line endings, no trailing whitespace. Pre-commit fixers skip this folder,
  and a test enforces these rules (`tests/integration/test_corpus.py`).
- Structure: one `#` title, then `##` sections (hard chunk boundaries), optional `###`.
  Numbered lists are procedures (never split) and tables stay whole.

### Front-matter schema (`FrontMatter`, `extra = forbid`)

```yaml
doc_id: who-hh-001                # slug; must equal the file name
title: Hand Hygiene in Health Care Settings
source_org: WHO                   # WHO | CDC | NIH
version: "3.0"                    # dotted numeric
effective_date: 2023-05-05
topic: [hand-hygiene]             # ≥ 1 slug
audience: [clinical-staff]        # ≥ 1 slug
jurisdiction: global              # global | national | institutional
status: current                   # current (default) | superseded
supersedes: null                  # doc_id of the version this one replaces
synthetic: true                   # REQUIRED and must be true
```

## 4. Topic coverage

`†` = superseded version.

| Topic | WHO | CDC | NIH |
| --- | --- | --- | --- |
| `aefi-reporting` | who-aefi-001, who-aefi-002 | cdc-aefi-001, cdc-aefi-002 | nih-aefi-001 |
| `cold-chain` | who-cc-001, who-cc-002 | cdc-cc-001†, cdc-cc-002 | nih-cc-001, nih-cc-002 |
| `device-associated-infections` | who-dai-001, who-dai-002 | cdc-dai-001 | nih-dai-001, nih-dai-002 |
| `environmental-cleaning` | who-env-001, who-env-002 | cdc-env-001 | nih-env-001, nih-env-002 |
| `hand-hygiene` | who-hh-001, who-hh-002 | cdc-hh-001 | nih-hh-001†, nih-hh-002, nih-hh-003 |
| `immunization-schedules` | who-imm-001, who-imm-002 | cdc-imm-001, cdc-imm-002 | nih-imm-001 |
| `injection-safety` | who-inj-001 | cdc-inj-001 | nih-inj-001 |
| `ipc-programme` | who-ipc-001 | cdc-ipc-001 | nih-ipc-001 |
| `occupational-health` | who-imm-001, who-imm-002, who-ohs-001 | cdc-shp-001, cdc-imm-002, cdc-ohs-001, cdc-ppe-002 | nih-imm-001, nih-ohs-001, nih-ppe-001, nih-shp-002 |
| `outbreak-response` | who-ob-001, who-ob-002 | cdc-ob-001, cdc-ob-002 | nih-ob-001 |
| `ppe` | who-ppe-001†, who-ppe-002 | cdc-ppe-001, cdc-ppe-002 | nih-ppe-001, nih-ppe-002 |
| `sharps-safety` | who-shp-001 | cdc-shp-001, cdc-shp-002 | nih-shp-001, nih-shp-002 |
| `sterilization` | who-ster-001 | cdc-ster-001, cdc-ster-002 | nih-ster-001, nih-ster-002 |
| `transmission-based-precautions` | who-tbp-001 | cdc-tbp-001, cdc-tbp-002 | nih-tbp-001, nih-tbp-002 |
| `waste-management` | who-hcw-001, who-hcw-002 | cdc-hcw-001, cdc-hcw-002 | nih-hcw-001 |

**Why three organisations per core topic:** ADR-0001 needs at least 4 relevant chunks per
answerable question for Precision@5 ≥ 0.65 to be achievable. Chunks here are roughly
section-sized, so a question such as *"how long should handrub be applied?"* is
answered by the matching section in each organisation's document (plus any superseded
version). In practice v1 gave only 2.7 relevant chunks per question, which is why v2
(§2a) added a second layer of documents; the v2 dev labels average 4.5 (P@5 ceiling 0.83).

## 5. Deliberate conflicts (superseded → current)

These exist to test citation behaviour now and version-aware retrieval and conflict
detection later (plan §9). The gold set must label which version an answer should cite.

| Old (status `superseded`) | New (`current`) | What changed |
| --- | --- | --- |
| `who-ppe-001` (v1.0, 2019) | `who-ppe-002` (v2.0, 2024) | Respirator fit test every **2 years → annually**; doffing changed from gloves-first to **gown and gloves together** |
| `cdc-cc-001` (v3.0, 2021) | `cdc-cc-002` (v4.0, 2025) | Twice-daily manual readings → **continuous data logger**; excursion report **within 24 h → immediately** |
| `nih-hh-001` (v1.0, 2018) | `nih-hh-002` (v2.0, 2023) | Handrub **15 s → 20–30 s**; alcohol **60–95% → 60–80%**; monthly manager audits → continuous independent observation |

Near-duplicate wording across organisations is also deliberate, e.g. `who-env-001` /
`cdc-env-001` (cleaning before disinfection) and `who-dai-001` / `cdc-dai-001`
(CLABSI insertion bundle), so that retrieval must rank between similar passages.

## 6. Adding or changing a document

1. Follow §3. Keep `##` sections at roughly 60–200 tokens.
2. Run `scripts/build-index.sh --inspect` and check the chunk statistics.
3. Run `scripts/test.sh --backend` (the corpus guards run there).
4. Update §4 and §5 of this card, then commit with `feat(corpus): …`. The new
   `index_version` makes gold labels for changed sections stale: re-check them (ADR-0001).
