# Phase 4 Report — Evaluation & Threshold Tuning

- **Date:** 2026-11-12 · **Plan ref:** `plan.md` §4 Phase 4 (brief Phase 3) · Milestone M1
- **Result:** the evaluation system is complete and runs in CI. On the held-out test-v2:
  **SC3 met** (pass rate 0.807); **SC2 not met as written** (P@5 0.417 against a best
  possible 0.583, i.e. 72% of the ceiling); **2 of 12** near-domain unanswerable questions
  were wrongly validated, both with identified causes. Full analysis:
  [`docs/evaluation-report.md`](../evaluation-report.md).
- **Needs decisions:** how SC2 is judged (OI-19), the ADR-0001/0002 approvals (OI-1, OI-2)
  and a label spot-check (OI-20).

## 1. Deliverables

| Plan item | Status | Where |
| --- | --- | --- |
| Gold dev/test sets + `DATASET_CARD.md` | ✅ 144-question dev pool, 95-question held-out test-v2; graded, section-level labels | `backend/evaluation/datasets/` |
| `eval_retrieval.py`: P@1/3/5/10, R@K, MRR, nDCG@5, Hit@5, per-topic and per-kind, bootstrap CIs | ✅ plus the P@5 ceiling and P@5 as a share of it | `backend/evaluation/eval_retrieval.py`, `metrics.py` |
| `eval_validation.py`: pass rate, confidence, histogram, abstention recall, false-validation rate | ✅ plus grounded pass rate and keyword recall | `backend/evaluation/eval_validation.py` |
| `threshold_sweep.py`: τ 0.30–0.90 curve and recommended τ | ✅ plus a constrained weight search; dependency-free SVG plot | `threshold_sweep.py`, `svg.py` |
| Ablation table | ✅ retrieval modes × expansion, RRF weights, BM25 parameters, heading boost, chunk size. SVD embedder not built (OI-10) | Evaluation report §3 |
| `reports/<run_id>/`: metrics, per-query CSV, **`low_confidence.csv`**, plots | ✅ | `backend/evaluation/run.py` |
| Eval runs prepared for the `eval_runs` table (Phase 5) | ✅ each run writes one `summary.json` with config, git revision and index version | `run.py` |
| `docs/evaluation-report.md` | ✅ | `docs/` |
| CI quality gate | ✅ `evaluation` job: no regression on the dev pool and no false validations there; literal targets printed every run (§3) | `.github/workflows/ci.yml`, `evaluation/baseline.json` |
| Scripts | ✅ `scripts/eval.sh` / `eval.ps1` (`--split`, `--gate`, `--update-baseline`, `--require-targets`) | `scripts/` |

## 2. Results

| | Dev pool | test-v1 (spent, earlier config) | **test-v2 (official)** |
| --- | --- | --- | --- |
| P@5 (ceiling) | 0.602 (0.826) | 0.593 (0.821) | **0.417 (0.583)** |
| P@5 / ceiling | 73% | 72% | **72%** |
| Hit@5 · MRR · nDCG@5 | 0.992 · 0.896 · 0.790 | 0.983 · 0.887 · 0.783 | **0.952 · 0.855 · 0.784** |
| Pass rate at τ = 0.6 | 0.926 | 0.702 | **0.807** [0.723, 0.892] |
| False validations | 0 / 22 | 0 / 11 | **2 / 12** |

## 3. What changed in the product

| Area | Change | Why |
| --- | --- | --- |
| Corpus | v2: 30 documents added (72 total, 346 chunks), `index_version` 6ce73ffaf982 | Honest labels on v1 capped P@5 at 0.54 (corpus card §2a) |
| Retrieval | BM25 + expansion ranks; dense vote 0 (`RRF_WEIGHT_*`, weighted RRF) | Best on every dev metric (ADR-0011) |
| Query expansion | v2: five lay synonym groups (flu, fake nails, beard, C. diff, kitchen/household) | Found on dev questions |
| Validation | Filler words removed from key terms; query support from the best single cited chunk | AUC 0.952 → 0.983 (ADR-0002 Revision 2) |
| Confidence weights | 0.40/0.35/0.25 → **0.20/0.60/0.20**; τ 0.6 and floor 0.15 unchanged | 5-fold CV on the dev pool |

The API contract did not change (still 1.1.0). `meta.signals.query_support` now uses
the best single cited chunk, as documented in ADR-0002.

## 4. Open issues closed in this phase

| # | Outcome |
| --- | --- |
| OI-3 | Off-topic medication questions now abstain (0 / 22 false validations on the dev pool). The remaining near-domain failures are tracked as OI-17 and OI-18 |
| OI-4 | Synonym groups added for the lay words found on dev ("flu", "fake nails", "beard", "C. diff", "kitchen") |
| OI-5 | MMR λ checked on dev (0.5–1.0): 0.7 stays best for pass rate and grounded pass rate |
| OI-6 | Weights tuned with 5-fold CV; τ and floor kept (evaluation report §4) |
| OI-7 | BM25 + expansion adopted as the ranking default (ADR-0011) |

## 5. Process notes (for the reviewer)

* **Two decisions were taken with the owner during the phase.** The first was to both grow
  the corpus and report cap-aware metrics. The second was, after test-v1 under-performed,
  to write a fresh test set rather than re-tune on test results.
* **test-v1 was spent honestly.** The first configuration over-fitted a 65-question dev
  split (0.892 dev vs 0.702 test). It is archived (`docs/evaluation/test-v1-results.json`)
  and the lesson changed the method: cross-validation on the full pool, test-v2 written
  before further tuning.
* **One exploratory run printed test-v1 retrieval numbers** while checking whether smaller
  chunks could lift the ceiling. No decision used them, and smaller chunks were rejected
  on dev evidence (nDCG falls).
* **test-v2 was revised once before its first use** (17 items replaced to follow the dev
  authoring protocol; DATASET_CARD §5). Its hash was recorded before tuning resumed.

## 6. Verification

| Check | Result |
| --- | --- |
| Backend tests | **268 passed** (Phase 3: 248) |
| ruff · ruff format · mypy --strict (98 files) | clean |
| Gold files current (`build_gold --check`) | yes |
| SC1 determinism on corpus v2 | 3 builds byte-identical, `index_version` 6ce73ffaf982 |
| Evaluation gate (bash and PowerShell) | passes against `baseline.json` |

## 7. Hand-off to Phase 4.1 / Phase 5

Phase 5 (persistence, auth, admin APIs) can start: the `summary.json` and
`low_confidence.csv` outputs map directly to the `eval_runs` table and the review queue.
Before claiming better safety numbers, a short Phase 4.1 should fix OI-17 and OI-18 on dev
and confirm them on a new test-v3 (OI-21). After the merge, run `scripts/build-index.sh`
once, because the corpus changed.
