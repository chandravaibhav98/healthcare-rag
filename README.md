# Healthcare Guidelines RAG Assistant — Rapid Query & Validation System

> ⚠️ **Not for clinical use.** All guideline content in this repository is **synthetic**
> (WHO/NIH/CDC-*style*, not real guidance). The system is a research and engineering
> prototype. Never use its output to make patient-care decisions.

A citation-first question-answering service over guideline documents. It answers
**only** from retrieved evidence, scores every answer for support, and **abstains**
(`status: needs_review`) when that support is weak.

## Status

| Stage | State |
| --- | --- |
| Pre-Phase 0 — project initialisation | ✅ Complete — see [`docs/project/phase-0-readiness.md`](docs/project/phase-0-readiness.md) |
| Phase 0 — foundations, contracts & decisions | ⏭️ Next |

## Where to start

| Document | Purpose |
| --- | --- |
| [`plan.md`](plan.md) | Delivery plan (Phases 0–12), architecture, ADR summaries, risks |
| [`docs/project/brief.md`](docs/project/brief.md) | The original project brief (source of truth for requirements) |
| [`docs/project/phase-0-readiness.md`](docs/project/phase-0-readiness.md) | Pre-flight results, environment setup, open questions |
| [`docs/adr/`](docs/adr/README.md) | Architecture Decision Records |

## Pre-flight check

Run this before any Phase 0 work (it only reads your environment and changes nothing):

```bash
./scripts/preflight.sh            # Linux / macOS / WSL / Git Bash
```

```powershell
pwsh ./scripts/preflight.ps1      # Windows (PowerShell 7+)
```

Quick start, configuration and the full scripts index are added in Phase 0
(`scripts/setup.*`) and completed in Phase 12.
