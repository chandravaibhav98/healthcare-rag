> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Deployment

Three targets share the same images and configuration keys. Operational procedures
(upgrade, rollback, index release, alerts) are in the [RUNBOOK](../RUNBOOK.md);
manifest-level detail is in [`deploy/README.md`](../deploy/README.md); the release
pipeline is in [releasing.md](releasing.md).

## 1. Targets

| Target | Command | Web | API | Database | Index |
| --- | --- | --- | --- | --- | --- |
| Local dev | `scripts/dev.sh` | http://localhost:5173 | http://localhost:8000 | SQLite (`artifacts/app.db`) | `scripts/build-index.sh` → `artifacts/index` |
| Docker Compose | `scripts/docker-up.sh` | http://localhost:8080 | behind nginx at `/api` | PostgreSQL 18 container | one-shot `indexer` service → named volume |
| Kubernetes (kind) | `scripts/k8s-up.sh` | http://localhost:8088 | behind Envoy Gateway at `/api` | PostgreSQL StatefulSet (local overlay) | `rag-index:<version>` image copied by an init container |
| Production | `kustomize build deploy/k8s/overlays/prod` | your Gateway + TLS | — | managed PostgreSQL via External Secrets | `rag-index:<version>` pinned by digest |

The same index version (for example `6ce73ffaf982`) and the same answers are produced on
every target; that is SC1 in practice.

## 2. Local dev

```bash
scripts/setup.sh                     # tools, .venv, node_modules, .env
scripts/build-index.sh
scripts/db-migrate.sh && scripts/seed.sh --demo
scripts/dev.sh
scripts/smoke.sh --base-url http://localhost:8000
```

## 3. Docker Compose (`deploy/compose/`)

Services: `postgres` → `migrate` (one-shot) → `indexer` (one-shot) → `api` → `web`
(nginx-unprivileged). Optional observability profile adds Prometheus and Grafana with a
provisioned RAG dashboard.

```bash
scripts/docker-up.sh --demo                 # build, start, seed demo data
scripts/docker-up.sh --observability        # + Prometheus / Grafana
scripts/docker-logs.sh api
scripts/docker-down.sh --volumes            # stop and delete data
```

## 4. Kubernetes (`deploy/k8s/`)

- `base/`: namespace (Pod Security Admission `restricted`), API Deployment (2 replicas,
  probes, non-root, read-only root filesystem), web Deployment, ConfigMap, migration Job,
  HPA (2–6 replicas), PDB, NetworkPolicies (web → api → postgres only), ServiceAccounts,
  Gateway API `Gateway` + `HTTPRoute`.
- `overlays/local/`: kind, Envoy Gateway, in-cluster PostgreSQL, seed Job,
  `secrets.env` (copy from `secrets.env.example`).
- `overlays/prod/`: managed database via `ExternalSecret`, TLS Gateway, larger resources.
  Rendered by the release workflow, pinned by digest.

```bash
scripts/k8s-up.sh                   # kind cluster, build + load images, apply, wait
scripts/k8s-status.sh
scripts/k8s-verify.sh               # zero failed requests during restart and index rollout/rollback
scripts/k8s-down.sh
```

## 5. Configuration and secrets

All keys: [`.env.example`](../.env.example). In Kubernetes, non-secret keys are in the
ConfigMap and secrets (`JWT_SECRET`, `DATABASE_URL`, seed password) in a Secret. Never
bake secrets into images. Production requires `APP_ENV=production`, a strong
`JWT_SECRET`, `LOG_QUESTION_TEXT=false` and `AUTH_COOKIE_SECURE=true`.

## 6. Known issues

- The `rag-web` image scan reports nginx CVEs that wait for an upstream fix (F-19). The
  owner chose to wait rather than suppress them; see the
  [test plan Open Items](../test-plan.md#open-items).
