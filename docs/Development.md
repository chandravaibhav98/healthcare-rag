> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Development

How to set up a machine, make a change and get it merged. Working rules are in
[CONTRIBUTING.md](../CONTRIBUTING.md).

## 1. Prerequisites

uv (Python 3.12), Node.js 26, Docker, and for later stages kind, kubectl, k6 and ffmpeg.
`scripts/preflight.sh` checks them without changing anything.

## 2. First run

```bash
scripts/setup.sh          # .venv, node_modules, Playwright browsers, .env from .env.example, pre-commit hooks
scripts/build-index.sh
scripts/db-migrate.sh && scripts/seed.sh --demo
scripts/dev.sh            # API :8000, web :5173
```

Demo accounts and passwords come from `.env` (`SEED_ADMIN_*`) and `scripts/seed.sh --demo`.

## 3. Daily loop

| Task | Command |
| --- | --- |
| Lint and type-check | `scripts/lint.sh` (`--fix`) |
| Tests | `scripts/test.sh --backend` / `--frontend` / `--e2e` / `--all` |
| After an API schema change | bump `CONTRACT_VERSION`, then `scripts/gen-client.sh` |
| After a corpus or index-config change | `scripts/build-index.sh`, `scripts/verify-determinism.sh` |
| After a retrieval or validation change | `scripts/eval.sh --split dev` (never tune on test) |
| Pre-commit hooks without a global install | `uvx pre-commit run --all-files` |

## 4. Branching and commits

- Trunk-based: short-lived branches, squash-merge to `main`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- The `ci-passed` check must be green. Branch rulesets need a public repository or a paid
  GitHub plan (see the test plan Open Items).

## 5. Windows notes

- Use Git Bash for `.sh` scripts or PowerShell 7 for `.ps1`.
- Prefix commands that pass `/c/...` paths to native tools with `MSYS_NO_PATHCONV=1`.
- Testcontainers needs Docker Desktop running; tests skip cleanly when it is not.

## 6. Where things are

[Backend.md](Backend.md) · [Frontend.md](Frontend.md) · [Database.md](Database.md) ·
[Scripts.md](Scripts.md) · [E2E.md](E2E.md) · [ADRs](adr/README.md)
