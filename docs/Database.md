> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Database

SQLAlchemy 2 (async) models in `backend/app/db/models.py`, migrations in
`backend/migrations/` (Alembic). SQLite is used for development and unit tests;
PostgreSQL 18 for Compose, Kubernetes and production (ADR-0008).

## 1. Tables

| Table | Holds | Written by |
| --- | --- | --- |
| `users` | Accounts, Argon2id hashes, role (`user`, `reviewer`, `admin`) | `seed`, admin |
| `refresh_tokens` | Refresh-token records (rotation and revocation) | auth service |
| `query_log` | Every `/qa` call: **redacted** question, status, confidence, signals, citations, latency, index version, withheld candidate answer, escalation fields | query-log writer |
| `reviews` | Reviewer verdicts (approve, reject, correct), notes, corrected citations | review queue |
| `eval_runs` | Evaluation runs and their metrics | eval service |
| `index_versions` | Published index versions, manifests, active flag | index service |
| `audit_log` | Who changed what (config, index activation, reviews) | admin services |
| `app_config` | Versioned runtime config (threshold, weights) with an optimistic lock | settings page |

## 2. Migrations

| Revision | Change |
| --- | --- |
| `0001_initial_schema` | All tables above |
| `0002_query_escalation` | User escalation fields on `query_log` (contract 1.3) |

```bash
scripts/db-migrate.sh               # upgrade to head
scripts/db-migrate.sh --current     # show the current revision
scripts/db-migrate.sh --downgrade --revision 0001
```

In Compose a one-shot `migrate` service runs before the API; in Kubernetes a migration
Job runs before rollout.

## 3. Configuration

| Key | Default |
| --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///artifacts/app.db` (dev); `postgresql+asyncpg://…` elsewhere |
| `QUERY_LOG_RETENTION_DAYS` | 30 |
| `RETENTION_PURGE_INTERVAL_MINUTES` | 60 |
| `QUERY_LOG_QUEUE_SIZE` | 10000 |
| `CONFIG_POLL_SECONDS` | 30 (pods pick up runtime config changes) |

## 4. Data protection

- Questions pass through PHI redaction (`app/core/redaction.py`) before they are stored.
- Rows older than the retention period are purged by a background task.
- Backups, restore and retention operations: [RUNBOOK §6.5–6.6](../RUNBOOK.md).

## 5. Seeding

`scripts/seed.sh` creates the admin account (`SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`).
`--demo` adds reviewer and user accounts and a week of query history; `--reset` clears
the database first.
