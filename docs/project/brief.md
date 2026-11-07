# Project Brief — Healthcare Guidelines RAG Assistant

> This is the original project brief, captured verbatim so that every requirement
> in `plan.md` can be traced back to it. **Do not edit it to match the
> implementation.** Record any change of scope as an ADR or as a change-log entry
> at the bottom of this file.

**Project title:** Healthcare Guidelines RAG Assistant — Rapid Query and Validation System

**Description:** Deliver a working Retrieval-Augmented Generation (RAG) system that can
answer healthcare-related queries based strictly on authoritative guideline documents
(e.g., WHO, NIH, CDC equivalents). The system must validate every generated response
against the retrieved evidence and abstain when confidence is low.

## Problem Context

Clinicians, administrators, and support staff frequently require immediate reference
answers from standard medical guidelines — such as infection control (IPC) protocols,
PPE use, and vaccination procedures. Manual searches delay response time and risk
inconsistent interpretation. The goal is to operationalize a citation-first,
evidence-validated query assistant that can later plug into the organization's internal
document gateway (containing WHO/NIH/CDC guidelines).

The project runs entirely on a synthetic guideline corpus to maintain confidentiality,
while all code, APIs, and evaluation layers are production-ready.

## Implementation Plan (as briefed)

| Phase | Scope |
| --- | --- |
| 1 — Setup and Corpus Indexing | Load synthetic guideline corpus (WHO/NIH/CDC-style markdown files). Generate embeddings using `embeddings.py`. Build FAISS index using `scripts/pipeline.py`. |
| 2 — RAG Pipeline Integration | Implement retrieval logic and extractive QA generator. Construct the `/qa` endpoint returning validated answers. Integrate coverage-based validator and confidence scoring. |
| 3 — Evaluation and Threshold Tuning | Run Precision@K tests (`evaluation/eval_retrieval.py`). Tune coverage threshold (default 0.6) to optimize validated vs. abstained answers. Document validation results in summary report. |
| 4 — Packaging and Documentation | Ensure endpoint reliability and consistent schema. Finalize README and RUNBOOK with detailed deployment instructions. Prepare optional Streamlit UI (if time permits). |
| 5 — Final Review and Submission | Deliver working service and evaluation logs. Submit validation metrics and technical summary. |

## Success Criteria

| ID | Criterion |
| --- | --- |
| SC1 | 100% reproducible deterministic indexing (no API dependency). |
| SC2 | ≥ 0.65 Precision@5 on retrieval. |
| SC3 | ≥ 80% validation pass rate at threshold 0.6. |
| SC4 | Stable, REST-compliant FastAPI endpoint returning structured JSON. |

## Deliverables

| ID | Deliverable |
| --- | --- |
| D1 | **Working RAG API (FastAPI service)** — Endpoint `POST /qa`. Input `{ question, top_k }`. Output `{ answer, citations, confidence, status }`, where `status ∈ {validated, needs_review}` is determined by a confidence threshold (default 0.6). |
| D2 | **Deterministic embedding & index layer** — FAISS index built from synthetic markdown guidelines; deterministic 256-D embeddings (no external API calls). |
| D3 | **Validation & confidence engine** — Compute token-level overlap between the generated answer and retrieved guideline text; automatically flag weakly supported answers as `needs_review`. |
| D4 | **Evaluation reports** — Retrieval Precision@K; mean confidence and pass rate at threshold; list of low-confidence queries for analyst review. |
| D5 | **Deployment and integration artifacts** — `RUNBOOK.md` explaining how to swap in secure real guideline repositories; optional `docker-compose.yml` for reproducible setup. |

> The deliverable IDs D1–D5 are added here for traceability. `plan.md` §1.2 refers to them.

## Change Log

| Date | Change | Reference |
| --- | --- | --- |
| 2026-11-07 | Brief captured at project initialisation | — |
