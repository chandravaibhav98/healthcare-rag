# Working Agreements

How this project is developed day to day. Read this before contributing, and before
producing commands or files for the project (it also serves as the assistant's reference).

## 1. Primary shell: **Git Bash** (decided 2026-11-07, before Phase 1)

| Topic | Agreement |
| --- | --- |
| Day-to-day shell on Windows | **Git Bash** (`bash`). All commands in docs, READMEs, reports and reviews are written in **bash syntax** first. |
| PowerShell | The `.ps1` scripts stay as first-class parity twins. CI runs them on Windows for every PR, so they cannot rot. Write PowerShell commands only where nothing else works (e.g. Windows registry settings). |
| Script invocation | `scripts/<name>.sh` from the repo root (e.g. `scripts/setup.sh`, `scripts/test.sh --backend`). |
| Paths in docs | Forward slashes, repo-relative (`backend/app/rag/`), never `C:\...`. |

### Git Bash setup (one-time)

```bash
# Node 26 via fnm: add to ~/.bashrc (Git Bash sources it through ~/.bash_profile)
echo 'eval "$(fnm env --use-on-cd --shell bash)"' >> ~/.bashrc
# Long paths for git (Windows long paths must also be enabled; see phase-0-readiness.md §3)
git config --global core.longpaths true
# Reopen Git Bash, then from the repo root:
scripts/preflight.sh && scripts/setup.sh
```

### Git Bash pitfalls handled by the scripts

| Pitfall | Handling |
| --- | --- |
| Python prints `›`, `—` or `°C` through a pipe under mintty with the legacy code page (cp1252) and crashes with `UnicodeEncodeError` | `scripts/lib/common.sh` exports `PYTHONUTF8=1` (UTF-8 mode). Code also always passes `encoding="utf-8"` explicitly. |
| MSYS converts arguments that look like POSIX paths (`/api`) into Windows paths when calling native `.exe` tools | Scripts pass repo-relative or `$REPO_ROOT`-based paths. When a literal `/x` argument must reach a native tool unchanged, prefix the call with `MSYS_NO_PATHCONV=1`. |
| CRLF checkouts | `.gitattributes` forces LF. The index build also normalises CRLF → LF in memory, so `index_version` is identical even on a CRLF checkout (SC1). |
| `chmod +x` is not recorded on Windows | Mark new `.sh` files executable in Git: `git update-index --chmod=+x scripts/<name>.sh`. |

## 2. Collaboration conventions

- The assistant writes files **straight into the repository** and verifies them on a
  clean clone (Linux VM, plus PowerShell parity) before handing over. You review, commit
  and push.
- Every phase ends with `docs/project/phase-<n>-report.md`: deliverables, evidence,
  deviations, and your remaining actions.
- Decisions that cut across phases become ADRs (`docs/adr/`). Smaller choices go in the
  phase report.
- Conventional Commits and trunk-based flow, as described in `CONTRIBUTING.md`.
