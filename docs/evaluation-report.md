# Evaluation Report: final (Phase 12)

- **Status:** final. These are the numbers submitted with the project. They were produced
  in Phase 4 (2026-11-12) and **re-run unchanged in Phase 12 (2026-11-20)**. Nothing
  after Phase 4 changed retrieval, generation, validation or their configuration, and
  `scripts/reproduce.sh` checks this on every run (§9).
- **Index:** `6ce73ffaf982` (corpus v2, 72 documents, 346 chunks) · **Configuration:** BM25
  + query expansion; confidence weights (0.20, 0.60, 0.20); τ = 0.6; retrieval floor 0.15.
- **Plan ref:** `plan.md` §4 Phases 4 and 12 · ADR-0001 (relevance), ADR-0002 (confidence)
- **Reproduce:** `scripts/reproduce.sh --quick` (metrics in about 3 minutes) or
  `scripts/eval.sh --split dev|test`. Raw outputs: `backend/evaluation/reports/<run>/`
  (not committed); archived results: [`docs/evaluation/`](evaluation/).

## 1. Summary

| Criterion | Target | Dev pool (n = 122 + 22) | **Held-out test-v2 (n = 83 + 12)** | Status |
| --- | --- | --- | --- | --- |
| SC1 deterministic index | byte-identical | 3 rebuilds identical | — | ✅ Met |
| SC2 Precision@5 | ≥ 0.65 | 0.602 [0.561, 0.643] | **0.417 [0.371, 0.463]** | ❌ Not met as written (see §3.1) |
| … best possible P@5 (ceiling) | — | 0.826 | 0.583 | |
| … P@5 as share of ceiling | — | 73% | **72%** | stable across every question set |
| … Hit@5 / MRR / nDCG@5 | — | 0.992 / 0.896 / 0.790 | **0.952 / 0.855 / 0.784** | |
| SC3 pass rate at τ = 0.6 | ≥ 0.80 | 0.926 [0.877, 0.967] | **0.807 [0.723, 0.892]** | ✅ Met (CI lower bound below 0.80) |
| Safety: false validations | ≤ 5% (plan) | 0.000 (0 / 22) | **0.167 (2 / 12)** | ❌ Not met on test-v2 (§6) |
| SC4 REST contract | 0 violations | — | — | ✅ Met (Phase 3) |

Numbers in brackets are 95% percentile-bootstrap confidence intervals over questions
(2,000 resamples, fixed seed).

**Bottom line.** Retrieval nearly always finds the answer-bearing chunk (Hit@5 0.95–0.99),
and the validator passes 81% of answerable held-out questions. SC2's literal P@5 target is
out of reach for honest labels on this corpus: even a perfect retriever would score 0.58
on test-v2 and 0.83 on dev. The system reaches 72–73% of whatever is possible on every
question set. The most important open problem is safety: 2 of 12 near-domain unanswerable
test questions were answered (§6), and both have identified causes.

## 2. Method

* **Gold data** (`backend/evaluation/datasets/DATASET_CARD.md`): section-level, graded
  relevance (ADR-0001), labelled by reading chunk texts, blind to system output.
* **Protocol:** every choice is made on the development pool and frozen before a test
  split is run, once. When a test split has been used it is spent and joins the pool.
  test-v1 was spent this way (§5); test-v2 is the official result.
* **Pipeline under test:** the real `QAService` (the same code as `/qa`), in-process, with
  `top_k = 5`. Retrieval metrics use the ranked list from the same retriever.
* **Metrics:** P@K and R@K over grade ≥ 1; nDCG@5 with grades as gains; Hit@5 and MRR on
  grade 2 only; ceiling@5 = mean(min(|R|, 5)) / 5. Validation: pass rate = share of
  answerable questions returned `validated`; grounded pass rate additionally requires a
  grade-2 citation; false-validation rate = share of unanswerable questions validated.

## 3. Retrieval

### 3.1 Why P@5 cannot reach 0.65 here

P@5 for a question can never exceed |R|/5, where |R| is its number of relevant chunks.
With honest section-level labels on corpus v1, the average question had 2.7 relevant
chunks and the **ceiling was 0.54**. A smaller chunk size raises the ceiling without
helping users, which is metric-gaming (labels v1, dev questions):

| Chunk size (tokens) | Chunks | P@5 | Ceiling | nDCG@5 |
| --- | --- | --- | --- | --- |
| 80–160 (default) | 209 | 0.354 | 0.538 | 0.705 |
| 40–80 | 269 | 0.400 | 0.658 | 0.667 |
| 20–40 | 521 | 0.520 | 0.880 | 0.627 |

Corpus v2 instead added realistic redundancy (pocket guides, quick references and ward
procedures; corpus card §2a), which raised the dev ceiling to 0.83. The test-v2 questions
target more single-source facts, so their ceiling is 0.58. Raw P@5 therefore measures the
question set as much as the retriever, while **P@5 / ceiling is stable at 0.72–0.73**
across dev, test-v1 and test-v2. This is the evidence behind the proposal to read SC2 as
ceiling-normalised P@5 (ADR-0001, Phase 4 evidence; `plan.md` §10).

### 3.2 Ablation (dev questions of the v1 split, corpus v2, n = 65)

| Retriever | Expansion | P@5 | Hit@5 | nDCG@5 |
| --- | --- | --- | --- | --- |
| Hybrid RRF (dense + BM25, equal votes) | yes | 0.505 | 0.939 | 0.684 |
| Hybrid RRF | no | 0.526 | 0.923 | 0.685 |
| Dense only (256-D hashed) | yes | 0.415 | 0.862 | 0.569 |
| Dense only | no | 0.446 | 0.831 | 0.589 |
| **BM25 only (adopted)** | **yes** | **0.603** | **1.000** | **0.790** |
| BM25 only | no | 0.600 | 1.000 | 0.781 |

Weighted RRF (`RRF_WEIGHT_DENSE` 0 → 1 in 0.25 steps, k ∈ {10, 30, 60}) lowered P@5
monotonically from 0.603 to 0.505. BM25 parameters (k1 0.6–2.0, b 0.3–0.9) and boosting
headings (×1–3) moved P@5 by less than 0.01, so the defaults stay; I stopped there to
avoid over-tuning. **Decision:** BM25 + query expansion ranks; the hashed dense vectors
remain in the index for the validator's retrieval score (§4) and as a fusion option
(ADR-0004 Amendment 1). The SVD embedder ablation (OI-10) was not built.

## 4. Validation and threshold

### 4.1 Signals

On the 144-question dev pool, the area under the ROC curve for separating answerable from
unanswerable questions (among questions that reached generation) was:

| Signal | AUC |
| --- | --- |
| coverage (answer tokens found in the cited text) | 0.50: ≈ 1.0 for every extractive answer (ADR-0002) |
| retrieval score (cosine, best cited chunk) | 0.81 |
| query support, IDF-weighted, over all cited chunks combined | 0.952 |
| **query support, IDF-weighted, best single cited chunk (adopted)** | **0.983** |
| normalised BM25 score of the best cited chunk | 0.945 |

Two changes made query support sharper:

1. **Filler words removed** from question key terms ("got", "goes", "happen", "ever",
   "far" …; 49 words in `QUESTION_FILLER`). They are rare in guideline text, so IDF made
   them look like the most important terms of a lay question and penalised valid
   paraphrases. On the v1 dev split this raised the best pass rate with no false
   validations from 0.80 to 0.85.
2. **Best single chunk instead of the union.** A real answer usually has one passage that
   covers the whole question; an off-topic question collects partial matches from
   several chunks, and the union over-credits it.

Five lay synonym groups found on dev were also added to the expansion map ("flu",
"fake nails", "beard", "C. diff", "kitchen/household").

### 4.2 Choosing the weights

The rule was fixed in code (`evaluation/threshold_sweep.py`): τ stays at 0.6 because SC3
is defined there; coverage keeps a weight ≥ 0.2 because the brief requires
coverage-based validation (unconstrained, the search drops coverage entirely); maximise
the pass rate subject to ≤ 5% false validations.

| Feature set (coverage, support, retrieval) | 5-fold CV pass rate | 5-fold CV false validations |
| --- | --- | --- |
| coverage, union support, cosine (Phase 3 signals) | 0.850 (worst fold 0.708) | 0.040 |
| **coverage, best-chunk support, cosine (adopted)** | **0.934 (worst fold 0.875)** | **0.040** |
| coverage, union support, BM25-normalised | 0.975 | 0.270 |

Adopted weights **(0.20, 0.60, 0.20)** at τ = 0.6: dev pool pass rate 0.926 with 0 / 22
false validations. Neighbouring weights behave smoothly (0.20 / 0.55 / 0.25: 0.902 and 0;
0.20 / 0.70 / 0.10: 0.951 and 0.045). The floor (0.15) and MMR λ (0.7) were checked on
dev and kept: floor 0.10 added one validated question and MMR alternatives were worse.

Threshold curves (dev, test-v2): [`threshold-sweep-dev.svg`](evaluation/threshold-sweep-dev.svg),
[`threshold-sweep-test-v2.svg`](evaluation/threshold-sweep-test-v2.svg).

## 5. What happened on test-v1 (spent)

The first frozen configuration (BM25; union support; weights 0.20 / 0.35 / 0.45; chosen
on a 65-question dev split) scored **pass rate 0.702 [0.579, 0.825]**, P@5 0.593 and 0
false validations on test-v1, against 0.892 on its dev split. The weights sat on a sharp
edge of the dev split: small changes swung the pass rate by 0.15. Rather than re-tune on
those results, test-v1 was declared spent, a new test set was written, and selection
moved to 5-fold cross-validation on the full 144-question pool, which is what §4 reports.
Archived: [`test-v1-results.json`](evaluation/test-v1-results.json).

## 6. Error analysis (test-v2, after the single run)

**False validations (2 of 12).** Both are near-domain questions:

| Question | Why it passed |
| --- | --- |
| "What is the hepatitis **A** vaccine schedule for health workers?" | "a" is a stop-word, so the question becomes "hepatitis vaccine schedule health workers", which the hepatitis B guidance supports fully. A single-letter distinguisher is lost. |
| "What is the incubation period of **measles**?" | "measles" and "incubation period" both occur in the corpus, but never together; bag-of-terms support cannot see that they never co-occur. |

**Abstained answerable questions (16 of 83).** 3 were below the retrieval floor and 13 had
low confidence. Paraphrases are the weak spot: pass rate 0.62 for paraphrase, 0.83 for
direct and 1.00 for acronym questions (n = 13 / 65 / 5).

These findings were **not** fed back into the configuration: test-v2 is spent, and fixes
need a new test set to be credited (§8).

## 7. Analyst review list

Every run writes `low_confidence.csv` with each wrong decision (abstained answerable,
false validation, validated without an answer-bearing citation) and every validated
answer within 0.05 of τ, including question, answer and citations. This is the
deliverable "list of low-confidence queries for analyst review" (brief D4).

## 8. Limitations and next steps

1. **Single annotator who built the system.** ADR-0001's ≥ 20% second-person spot-check is
   pending (mentor). The corpus v2 documents were also written after the dev questions
   (corpus card §2a).
2. **Small unanswerable sets** (22 dev, 12 test): the false-validation CI on test-v2 is
   [0.00, 0.42].
3. **Proposed fixes, to be evaluated on dev and confirmed on a new test-v3:**
   (a) keep single-letter and numeric qualifiers attached to their term ("hepatitis a",
   "type 2"); (b) a co-occurrence check: a question's main concepts must appear in the
   same cited sentence or chunk; (c) more lay paraphrase synonyms;
   (d) optionally an offline entailment model as a secondary check (ADR-0002 option C).
4. **SC2 reading** needs a mentor decision: literal P@5 versus P@5 relative to the
   ceiling (ADR-0001).

## 9. Reproducing these numbers

| What | Command | Expected |
| --- | --- | --- |
| Everything below, compared with the records, plus the submission bundle | `scripts/reproduce.sh` (`--quick` = metrics only) | `RESULTS.md` with "Reproduced exactly: yes" |
| SC1 | `scripts/verify-determinism.sh --runs 3` | `PASS 3 builds byte-identical · index_version 6ce73ffaf982` |
| Dev pool | `scripts/eval.sh --split dev` | equals `backend/evaluation/baseline.json` |
| Held-out test-v2 | `scripts/eval.sh --split test` | equals `docs/evaluation/test-v2-results.json` |

Re-running the held-out split with the frozen configuration only recomputes the
recorded numbers. Using it to choose a configuration would spend it (§5).

**Phase 12 re-run (2026-11-20, fresh index build):** dev P@5 0.602, Hit@5 0.992, pass
rate 0.926, false validations 0 / 22. Test-v2 P@5 0.417 (ceiling 0.583), Hit@5 0.952,
pass rate 0.807, false validations 2 / 12. These equal the records to four decimals,
bootstrap intervals included (fixed seed).

**Serving performance** (not a quality metric, recorded for completeness): `/qa` p95
179 ms under 50 virtual users for 5 minutes with 0% errors (Phase 7, k6); about 17 ms
for a single request.
