# Phase 0 Readiness — Pre-Phase 0 Initialisation Report

- **Date:** 2026-11-07
- **Scope:** everything that must be true *before* Phase 0 starts (`plan.md` §4).
  Phase 0 deliverables are listed at the end as the hand-off, not done here.

## 1. Pre-Phase 0 checklist

| # | Item | Why it must come before Phase 0 | Status |
| --- | --- | --- | --- |
| P1 | Requirements captured in the repo ([`brief.md`](brief.md)) | The plan's traceability matrix (§1.2) needs a fixed source of truth | ✅ Done |
| P2 | Plan versioned in the repo ([`plan.md`](../../plan.md), LF) | Phase work is tracked against a versioned plan, not a loose file | ✅ Done |
| P3 | `.gitattributes` (LF everywhere, binary artifacts) | Must exist **before the first commit** so history never holds CRLF corpus bytes (SC1) | ✅ Done |
| P4 | `.editorconfig`, `.gitignore` | Stop editors creating CRLF files and keep index artifacts and `.env` out of Git from day one | ✅ Done |
| P5 | Toolchain pins: `.python-version` (3.12), `.nvmrc` (26) | Phase 0 lockfiles (`uv.lock`, `package-lock.json`) are generated against these | ✅ Done |
| P6 | ADR process ([ADR-0000](../adr/0000-record-architecture-decisions.md), [template](../adr/template.md), [index](../adr/README.md)) | Phase 0 must draft ADR-001…009 and accept 001 and 002 | ✅ Done |
| P7 | Feasibility spike for R4, R5, R7 ([report](../spikes/2026-11-07-faiss-determinism.md)) | De-risks ADR-003 and ADR-005 before they are written | ✅ Done |
| P8 | Read-only pre-flight check (`scripts/preflight.sh` / `.ps1`) | Phase 0's `setup.*` builds on it; it finds machine problems early | ✅ Done |
| P9 | Git repository initialised on `main` | Phase 0 starts with a commit history and trunk-based branching | ✅ Initialised · ⏳ **you** make the first commit (§3) |
| P10 | Toolchain installed on the Windows dev machine | Phase 0 exit criterion: a clean machine reaches "lint + tests green" | ⏳ **You** run pre-flight (§3) |
| P11 | Open questions answered by mentor or stakeholder (§4) | Q1 and Q2 block Phase 0's exit (ADR-001 and ADR-002 must be Accepted) | ⏳ Ask before ADR sign-off |

## 2. Decisions taken at initialisation

| Decision | Rationale | Reversible? |
| --- | --- | --- |
| Repo root is a `healthcare-rag/` sub-folder, not the outer project folder | Matches §2.3 naming. The outer folder name has spaces, an em dash and is long, so a single sub-folder is easy to move to a short path | Yes: move the folder |
| Python **3.12** (per plan) | `faiss-cpu` 1.15.1 ships cp312 wheels for Windows and Linux. 3.12 is supported upstream until Oct 2028, longer than this project | Yes, before `uv.lock` exists |
| Node **26** | Plan says "current Node LTS". Node 26 entered Active LTS on 2026-10-28; Node 24 is now in maintenance | Yes, before `package-lock.json` exists |
| LF line endings for **all** text, including `.ps1` | One rule is easier to enforce. PowerShell 7 reads LF natively. Only `.bat`/`.cmd` use CRLF | Yes, with `git add --renormalize` |
| Repo-local Git config: `core.autocrlf=false`, `core.ignorecase=true`, `core.filemode=false` | `.gitattributes` owns line endings. The other two settings match Git for Windows on NTFS, because the repo was initialised from a Linux VM | Yes |
| The outer `Plan.md` is left untouched; the repo copy `plan.md` is canonical | Avoids two sources of truth drifting | Delete the outer copy once you have moved the repo |

## 3. Your actions on the Windows machine (≈15 minutes)

```powershell
# 1. Toolchain (skip anything already installed)
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id Schniz.fnm -e          # confirm `node --version` prints v26.x
winget install --id Microsoft.PowerShell -e     # provides `pwsh` (Windows ships only 5.1 as `powershell`)
# ⚠️ Close and reopen the terminal now so `pwsh`, `uv` and `node` are on PATH.
#    Check: pwsh --version  →  PowerShell 7.x
#    No winget? Use the MSI installer: https://aka.ms/powershell-release?tag=lts

# 2. Long paths: node_modules and Playwright paths can exceed 260 characters
#    (run in an *Administrator* PowerShell)
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' LongPathsEnabled 1
git config --global core.longpaths true

# 3. Recommended: move the repo to a short ASCII path (the current path is ~120 chars
#    with spaces and an em dash, which some Docker and kind tooling handle badly)
New-Item -ItemType Directory -Force C:\dev | Out-Null
Move-Item ".\healthcare-rag" C:\dev\healthcare-rag
Set-Location C:\dev\healthcare-rag

# 4. Pre-flight: must print "READY for Phase 0" (warnings about Phase 7+ tools are fine)
pwsh ./scripts/preflight.ps1

# 5. First commit (your own Git identity)
git add -A
git update-index --chmod=+x scripts/preflight.sh
git commit -m "chore: initialise repository (pre-Phase 0)"
git ls-files --eol | Select-String "i/crlf"     # must print nothing

# 6. Optional: publish
# git remote add origin https://github.com/<you>/healthcare-rag.git
# git push -u origin main
```

> If you do not move the repo (step 3), pre-flight reports warnings for the path.
> Phase 0 can still proceed, but expect friction in Phase 8 (Docker) and Phase 9 (kind).

## 4. Open questions for the mentor or stakeholder

| # | Question | Why it matters | Default if there is no answer |
| --- | --- | --- | --- |
| **Q1** | May Precision@5 use **section-level relevance** (all chunks of the gold section count)? | With one gold chunk per question, P@5 ≤ 0.20, so SC2 (≥ 0.65) is impossible by construction | Section-level + graded qrels (ADR-001 option B+C) |
| **Q2** | The brief defines validation as *token-level overlap*. May confidence **blend** overlap with query support and retrieval score, provided overlap is still computed and reported? | For extractive answers overlap is ≈ 1.0 by construction, so SC3 would be meaningless on its own | Composite score + numeric gate (ADR-002); raw coverage shown in `meta.signals` |
| Q3 | Is `POST /qa` required at the root, or is `/api/v1/qa` acceptable? | API contract (SC4, D1) | Serve both; `/qa` is an alias |
| Q4 | Is the React admin dashboard and Kubernetes scope welcome, or should the Streamlit option be preferred? | Timeline: about 5–6 weeks versus about 2 weeks to milestone M1 | M1 first, extras after (plan §7 cut list) |
| Q5 | Where is the repo hosted, and are GitHub Actions (including Windows runners) available? | The CI determinism gate needs a Windows runner | GitHub, private repo |
| Q6 | May the synthetic corpus be drafted with LLM assistance offline (then committed and frozen)? | Corpus authoring effort in Phase 1 | Yes, labelled `synthetic: true` |

## 5. Hand-off: Phase 0 work order

Phase 0 deliverables (from `plan.md` §4), in the recommended order:

1. Answer **Q1 and Q2**, then write ADR-0001 and ADR-0002 → *Accepted*.
2. Create the monorepo skeleton per §2.3 (`backend/`, `frontend/`, `corpus/`, `e2e/`, `deploy/`, `.github/`).
3. `backend/pyproject.toml` + `uv.lock`; `frontend/package.json` + lockfile.
4. `.env.example` with every config key documented.
5. API contract v1 (Pydantic schemas) and an `openapi.json` snapshot.
6. Gold-dataset schema.
7. `scripts/lib/common.*` and `scripts/setup.*` (calls `preflight.*` first).
8. Pre-commit hooks (ruff, mypy, eslint, prettier, detect-secrets).
9. CI skeleton (lint + typecheck + unit tests on every PR).
10. Draft ADR-0003 to ADR-0009, citing the spike.
11. Expand the README stub.

**Phase 0 exit:** `scripts/setup.sh` and `setup.ps1` take a clean machine to "lint and tests green", and ADR-0001 and ADR-0002 are Accepted.
