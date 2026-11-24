> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Deliverables

What the project brief asked for, where each item is, and its status.

| # | Deliverable (brief) | Where | Status |
| --- | --- | --- | --- |
| 1 | Working RAG API: `POST /qa`, input `{question, top_k}`, output `{answer, citations, confidence, status}` | `backend/app/api/routes/qa.py`, [API.md](API.md) | ✅ contract 1.3.3 |
| 2 | Deterministic embedding and index layer: 256-D, no external calls, FAISS | `backend/app/rag/embeddings.py`, `rag/index/`, `scripts/build-index.*` | ✅ SC1 |
| 3 | Validation and confidence engine: token-level overlap, weak answers flagged `needs_review` | `backend/app/rag/validation/` (ADR-0002) | ✅ |
| 4 | Evaluation reports: Precision@K, mean confidence and pass rate at τ, low-confidence list | `backend/evaluation/`, [evaluation report](evaluation-report.md) | ✅ (SC2 below target, see report §3.1) |
| 5 | RUNBOOK for swapping in a secure real guideline repository | [RUNBOOK §4](../RUNBOOK.md) | ✅ |
| 6 | Optional `docker-compose.yml` | `deploy/compose/`, [Deployment.md](Deployment.md) | ✅ |
| 7 | Optional Streamlit UI | Replaced by the React app ([Frontend.md](Frontend.md)) | ✅ superseded |
| 8 | Technical summary and validation metrics | [technical-summary.md](technical-summary.md) | ✅ |

## Beyond the brief

| Item | Where |
| --- | --- |
| Admin dashboard: review queue, query explorer, evaluation, index versions, audited settings | [Frontend.md](Frontend.md) |
| Auth, RBAC, PHI redaction, audit log | [Backend.md](Backend.md), ADR-0008, ADR-0009 |
| Kubernetes (kind + prod overlay), Gateway API, HPA, NetworkPolicies | [Deployment.md](Deployment.md) |
| CI/CD with quality gates, SBOMs, build-once-promote releases | [releasing.md](releasing.md) |
| Playwright E2E, axe gate, recorded demo video, k6 load test | [E2E.md](E2E.md) |
| Observability: Prometheus metrics, Grafana dashboard, alert rules | [RUNBOOK §6](../RUNBOOK.md) |
| Bash and PowerShell scripts for every task | [Scripts.md](Scripts.md) |

## Handoff bundle

Produced by `scripts/reproduce.sh` and the release workflow: tagged release, images,
evaluation logs, low-confidence list, demo MP4, Playwright report. Licensing is left to
the client (see the README).
