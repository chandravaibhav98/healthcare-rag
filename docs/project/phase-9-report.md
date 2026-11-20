# Phase 9 Report — Kubernetes Deployment

- **Date:** 2026-11-20 · **Plan ref:** `plan.md` §4 Phase 9 · Milestone M3 (part 2)
- **Result:** every deliverable is built. From an empty namespace, `scripts/k8s-up.sh`
  (and `.ps1`) deploys, migrates, seeds and smoke-tests the stack; the **E2E suite passes
  20/20 through the Gateway**; `scripts/k8s-verify.sh` (and `.ps1`) shows **zero failed
  requests** during a rolling restart and during an index rollout and rollback under k6
  load. **Exit criterion met** on k3s; the kind + Envoy Gateway path first runs in CI (OI-37).
- **Decisions:** ADR-0015. **Bug fixed:** index-version bookkeeping under image rollouts (§3).

## 1. Deliverables

| Deliverable | Where |
| --- | --- |
| Namespace (Pod Security **restricted** enforced), ServiceAccounts without tokens, ConfigMap | `deploy/k8s/base/` |
| API Deployment: init container copying `rag-index:<version>` into an `emptyDir`; startup/readiness/liveness probes; requests and limits; non-root, read-only root, no capabilities, RuntimeDefault seccomp; `maxUnavailable: 0`; `preStop`; topology spread; `enableServiceLinks: false` | `base/api.yaml` |
| Web Deployment and Services | `base/web.yaml` |
| `db-migrate` Job (Argo CD PreSync annotations) | `base/migrate-job.yaml` |
| HPA (CPU 70 %, 2–6), PDBs (`minAvailable: 1`) | `base/autoscaling.yaml` |
| NetworkPolicies: default deny; gateway → web, api; web → api; app → postgres | `base/networkpolicies.yaml`, `overlays/local/postgres.yaml` |
| Gateway API `Gateway` + `HTTPRoute` (`/api`, `/qa` → api; `/` → web) | `base/gateway.yaml` |
| Local overlay: PostgreSQL StatefulSet, seed Job, Envoy Gateway class + NodePort `EnvoyProxy`, generated Secret | `overlays/local/` |
| Prod overlay: `ExternalSecret`, HTTPS listener (cert-manager) + redirect, 3+ replicas, bigger resources, sign-in required, ServiceMonitor | `overlays/prod/` |
| Optional ServiceMonitor (+ NetworkPolicy for the monitoring namespace) | `components/service-monitor/` |
| kind cluster (1 + 2 nodes, `localhost:8088`) | `kind/cluster.yaml` |
| Scripts: `k8s-up`, `k8s-down`, `k8s-status`, `k8s-port-forward`, `k8s-verify` (bash + PowerShell) | `scripts/` |
| CI: `manifests` (kustomize + kubeconform, CRDs included) and `kubernetes` (kind, E2E, k8s-verify) | `.github/workflows/ci.yml` |

## 2. Verification

| Check | Result |
| --- | --- |
| `kubeconform -strict` on base, local, prod (CRD schemas from the catalog) | 17 / 24 / 21 resources, all valid |
| Envoy objects (`GatewayClass eg`, `EnvoyProxy`, `Gateway.infrastructure`) | Accepted by a server-side dry run against Envoy Gateway v1.10.0's CRDs |
| `k8s-up.sh` and `k8s-up.ps1` from an empty namespace | Built, loaded, applied; postgres → migrate → api/web → seed → Gateway Programmed; 7/7 smoke checks through the gateway |
| Pod Security `restricted` | Every pod admitted (namespace enforces it) |
| E2E through the Gateway | **20/20** |
| NetworkPolicies, probed from pods | Other namespace → api, web, postgres: all refused. Gateway namespace → api, web: open; → postgres: refused |
| Rolling restart of api + web under 20 VUs | **1,716 requests, 0 failed** (PowerShell run: 1,463, 0 failed) |
| Index rollout 6ce73ffaf982 → bfae4024806c and `rollout undo`, under 20 VUs | **1,746 requests, 0 failed**; 20 consecutive answers from the new index, then from the old one |
| Dashboard "active index" after rollout and rollback | Follows the deployment; audited as `index.activate`, reason `deployment` |
| HPA | Read CPU from metrics-server and scaled the API 2 → 3 under the verification load |

## 3. Defects found

| # | Found by | Defect | Fix |
| --- | --- | --- | --- |
| 1 | First apply | Kubernetes injected `API_PORT=tcp://10.43.x.x:8000` from the `api` Service, which the app's settings rejected: migrate Job and API crashed | `enableServiceLinks: false` on every pod |
| 2 | Design review of the index rollout | **Index-version bookkeeping assumed one host.** After an image rollout the DB still named the old version as active at the same path, so each pod would re-load the new files every poll and the dashboard would show the wrong index; old pods during a rollout would try to "follow" a version they do not have | The deployed index wins at start-up (audited); pods never follow a version whose files they lack; activating such a version is 409. `tests/integration/test_index_rollout.py` (SQLite + PostgreSQL) fails on the old code |
| 3 | k8s-verify | Checking the served index right after `rollout status` saw old pods for a few seconds (kept-alive connections to terminating pods) | The check waits for 20 consecutive matching answers (60 s limit); not a defect in the app |
| 4 | k8s-verify | A failed check could leave the candidate index deployed | The script rolls back on any failure |

## 4. Open issues

Closed: **OI-13** (ingress-nginx retired in March 2026; the Gateway API is used) and
**OI-15** (every `scripts/*.sh` is committed executable, mode 100755). New:
OI-37 (verified on k3s/Traefik and stand-in images; kind + Envoy in CI), OI-38 (no egress
policies). Updated: OI-11 (rate limits are per pod, now 2–6 pods).

## 5. How this was verified

The sandbox cannot pull from Docker Hub or GHCR, so kind's node image and Envoy
Gateway's images were unavailable. Verification used **k3s v1.37.2** (from GitHub
releases, with its air-gap image bundle), its **Traefik** Gateway API provider and its
kube-router NetworkPolicy controller. A verification-only overlay applied the delivered
local overlay unchanged except for three patches: delete the Envoy `GatewayClass` and
`EnvoyProxy`, set the class to `traefik`, and listen on Traefik's entry-point port. The
images were the Phase 8 builds on stand-in bases (OI-37). The VM lacked
`CAP_SYS_RESOURCE`, so a runc wrapper clamped kubelet's negative `oom_score_adj`; nothing
in the deliverables depends on that.
