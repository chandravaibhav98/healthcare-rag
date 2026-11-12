# Dataset Card — Gold Evaluation Questions

> All questions concern the **synthetic** guideline corpus (`corpus/`). They are not
> clinical questions about real guidance.

## 1. Purpose

Measure retrieval (SC2, Precision@5) and answer validation (SC3, pass rate at τ = 0.6),
and check that the system **abstains** on questions the corpus cannot answer.

## 2. Files

| File | Edited by hand? | Contents |
| --- | --- | --- |
| `gold_source.yaml` | **yes** | Development pool: 144 questions (122 answerable, 22 unanswerable) |
| `gold_test_source.yaml` | **yes, only before first use** | Held-out test-v2: 95 questions (83 answerable, 12 unanswerable) |
| `gold_dev.jsonl`, `gold_test.jsonl` | no (generated) | Validated `GoldItem` records (`evaluation/schemas.py`) |
| `gold_manifest.json` | no (generated) | Pinned `index_version`, SHA-256 of both sources, counts |
| `gold.schema.json` | no (generated) | JSON Schema of one record |

```bash
uv run python -m evaluation.build_gold            # regenerate after editing a YAML file
uv run python -m evaluation.build_gold --check    # CI: generated files must be current
```

## 3. Composition

| | Dev pool | Test-v2 |
| --- | --- | --- |
| Questions | 144 | 95 |
| Unanswerable | 22 (15%) | 12 (13%) |
| direct / paraphrase / acronym | 88 / 21 / 13 | 65 / 13 / 5 |
| Topics | all 15 | all 15 |
| Relevant chunks per answerable question (mean) | 4.5 | 3.0 |
| P@5 ceiling (best any retriever can score) | 0.826 | 0.583 |

Unanswerable questions mix clearly off-topic questions ("capital of Australia") with
**near-domain** ones that share vocabulary with the corpus but are not answered by it
("hepatitis A vaccine schedule", "incubation period of measles", "PPE for radioactive
waste"). The near-domain ones are the real test of abstention.

## 4. Annotation guide (ADR-0001)

A chunk is **relevant** to a question if it has a grade:

* **Grade 2, answer-bearing:** the chunk states the facts a correct answer needs. A
  chunk with a *different* value from another organisation still counts (for example a
  CDC "at least 15 seconds" chunk for a handwashing-duration question).
* **Grade 1, topically relevant:** the chunk covers the same procedure or subject and
  a clinician looking for the answer would want to read it, but it does not state the
  answer. Superseded versions of a grade-2 section are grade 1, because ADR-0010 never
  lets them supply answer text.
* Everything else is not relevant, including chunks from the same document about a
  different procedure.

Every answerable question needs at least one grade-2 chunk (schema-enforced).
Unanswerable questions have no relevant chunks. `expected_keywords` are diagnostic only
and never affect a metric used for a criterion.

**Labelled blind to the system:** labels were made by reading the chunk texts, not by
looking at what the retriever returned. No pooled judging was used; retrieved-but-
unlabelled chunks were inspected once (Phase 4 audit) and left unlabelled.

## 5. History (how the splits came to be)

1. **v1 (Phase 4 start):** 144 questions, stratified 76 dev / 68 test by topic.
   Labelling all 209 v1 chunks showed a P@5 ceiling of 0.54, so SC2 was impossible.
2. **Corpus v2:** 30 documents added (`corpus/CORPUS_CARD.md` §2a); the labels of all
   144 questions were extended by reading the 137 new chunks (ceiling 0.83).
3. **test-v1 used once** with the configuration frozen on dev: pass rate 0.702, P@5
   0.593 (`docs/evaluation/test-v1-results.json`). The dev-tuned weights had over-fitted
   a 65-question dev split. test-v1 was then **spent** and joined the development pool.
4. **test-v2 written** before any further tuning. Its first draft targeted mostly
   single-source secondary facts (ceiling 0.45); before its first use, 17 items were
   replaced to follow the dev authoring protocol (core guidance that several
   organisations cover). Its ceiling is still lower than dev's (0.58 vs 0.83). The file
   hash was recorded before tuning and is pinned in `gold_manifest.json`.
5. **test-v2 used once** with the configuration frozen on the dev pool (5-fold CV):
   the official Phase 4 result (`docs/evaluation/test-v2-results.json`). It is now spent
   too: the next claim needs a test-v3.

## 6. Known limitations

* **One annotator,** who also built the system. ADR-0001 asks for a second-person
  spot-check of ≥ 20% of items; it is pending (open issue in `plan.md` §10).
* **Small unanswerable sets** (22 dev, 12 test): one false validation moves the rate by
  4.5 or 8.3 points, so its confidence interval is wide.
* **Corpus authored after the questions** (v2); see the corpus card §2a.
* **Ceilings differ** between dev and test, so raw P@5 is not comparable across them;
  P@5 as a share of its ceiling is (0.73 dev, 0.72 test-v1, 0.72 test-v2).
