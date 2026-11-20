# ADR-0015 — Kubernetes deployment: Kustomize, Gateway API, index rollouts

- **Status:** Accepted (Phase 9)
- **Date:** 2026-11-20
- **Plan ref:** `plan.md` §4 Phase 9 · **Builds on:** ADR-0008, ADR-0014

## Context

The service must run on Kubernetes with zero-downtime updates, an index that can be
rolled out and rolled back like code, least-privilege networking, and a local cluster
that matches production closely enough for the E2E suite to be meaningful. The community
ingress-nginx controller, the usual default, was retired by Kubernetes SIG Network in
March 2026 and receives no further security fixes.

## Decision

| Concern | Choice | Why / alternative |
| --- | --- | --- |
| Packaging | Kustomize `base/` + `overlays/{local,prod}` + an optional `components/service-monitor` | Few variables, native to kubectl. Helm only if the chart is distributed |
| North-south | Gateway API (`Gateway` + `HTTPRoute`): `/api` and `/qa` → `api`, everything else → `web`. Local: Envoy Gateway v1.10.0 (`GatewayClass eg`), data plane as NodePort 30080 mapped by kind to `localhost:8088` | Portable routes; no Ingress controller to maintain. The class is the only implementation-specific part |
| Index distribution | Init container from `rag-index:<index_version>` copies into an `emptyDir`; the API hash-verifies it at start | The index tag is in the pod template, so `kubectl set image` rolls it out and `kubectl rollout undo` rolls it back |
| Index registry semantics | A pod that boots a different index than the DB's active one, whose recorded files it does not hold, makes its own index active (audited, reason `deployment`); a pod never follows an activation whose files it lacks; activating such a version is 409 | Found while designing the rollout: without it, old pods would re-load the same files every poll and the dashboard would name the wrong active index. Covered by `tests/integration/test_index_rollout.py` |
| Rollouts | `maxUnavailable: 0`, `maxSurge: 1`, readiness on `/readyz` (index + DB), startup probe for index verification, `preStop` sleep 5 s, PDBs `minAvailable: 1`, topology spread | Zero failed requests during restarts and index changes (verified under k6) |
| Scaling | HPA 2–6 on CPU 70 %, 5-minute scale-down stabilisation; the API Deployment has no `replicas` so `kubectl apply` never fights the HPA | Retrieval is CPU-bound |
| Pod security | Namespace enforces the `restricted` Pod Security Standard; every pod runs non-root, read-only root filesystem, no capabilities, `RuntimeDefault` seccomp, no service-account token, `enableServiceLinks: false` | The last one is not cosmetic: the `api` Service would inject `API_PORT=tcp://…`, which collides with the app's `API_PORT` setting |
| Network | Default-deny ingress; gateway namespace (label `healthcare-rag/gateway=true`) → web, api; web → api; api/migrate/seed → postgres | Verified: other namespaces cannot reach api, web or postgres; the gateway cannot reach postgres |
| Migrations | `db-migrate` Job before the rollout (Argo CD PreSync hook annotations); the API refuses to start on an old schema | Never two pods migrating concurrently |
| Database | Local: PostgreSQL StatefulSet with a PVC. Prod: managed PostgreSQL via `DATABASE_URL` | Operating a database is not this service's job in production |
| Secrets | Local: `secretGenerator` from a git-ignored, generated `secrets.env` (content hash in the name, so a change rolls the pods). Prod: `ExternalSecret` from a `ClusterSecretStore` | Nothing secret in Git |
| Prod overlay | HTTPS listener with a cert-manager certificate, HTTP→HTTPS redirect, 3+ replicas, larger resources, `ALLOW_ANONYMOUS_QA=false`, ServiceMonitor, image names set by the release pipeline | Applied by CI/GitOps (Phase 10), never from a laptop |

## Consequences

- `scripts/k8s-up.*` builds, loads and deploys from scratch; `scripts/k8s-verify.*` proves
  zero-downtime restarts and index rollback under load.
- Rate limits stay per pod (OI-11): with N replicas a client gets up to N times the limit.
- Pods only see the index of their own image: a store-built index (dev rebuild) cannot be
  activated cluster-wide. That is intended: production indexes are built by CI (ADR-0008).
