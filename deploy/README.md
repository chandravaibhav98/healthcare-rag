# deploy

| Path | Contents | Phase |
| --- | --- | --- |
| `docker/` | `api`, `web`, `index` Dockerfiles; `nginx/` site config and security headers | 8 ✅ |
| `compose/` | `docker-compose.yml`, the observability profile, Prometheus + Grafana provisioning | 8 ✅ |
| `k8s/` | Kustomize `base/`, `overlays/{local,prod}/`, `components/service-monitor/`, `kind/` | 9 ✅ |

Decisions: [ADR-0014](../docs/adr/0014-container-images-and-compose.md) (images, Compose),
[ADR-0015](../docs/adr/0015-kubernetes-deployment.md) (Kubernetes).

## Images

| Image | Base | Runs as | Contents |
| --- | --- | --- | --- |
| `rag-api:<tag>` | `python:3.12-slim` | 10001 | Locked runtime dependencies, `backend/app`, migrations, scripts, evaluation harness. Also runs the migration and seed jobs |
| `rag-web:<tag>` | `nginxinc/nginx-unprivileged:1.30-alpine` | 101 | The SPA build; proxies `/api`, `/qa`, `/healthz`, `/readyz`, `/version` to `api:8000` |
| `rag-index:<index_version>` | `busybox:1.37` | 65534 | The index files (`/index`) and a `cp` into `/target`. Same `index_version` as the CI determinism build |

```bash
docker build -f deploy/docker/api.Dockerfile   -t rag-api:local   .
docker build -f deploy/docker/web.Dockerfile   -t rag-web:local   .
docker build -f deploy/docker/index.Dockerfile -t rag-index:build .
docker run --rm rag-index:build cat /index/manifest.json   # index_version
```

All three run with a read-only root filesystem and no capabilities. Behind a proxy that
the build needs, pass flags to every build with `DOCKER_BUILD_ARGS` (e.g.
`--build-arg HTTPS_PROXY=...`).

## Docker Compose

```bash
scripts/docker-up.sh                    # build, start, seed admin, smoke test → http://localhost:8080
scripts/docker-up.sh --demo             # + reviewer/user accounts and a week of history (APP_ENV=staging)
scripts/docker-up.sh --observability    # + Prometheus :9090 and Grafana :3000
scripts/docker-logs.sh api --follow
scripts/docker-rebuild.sh               # after code changes; data kept
scripts/docker-down.sh [--volumes]      # --volumes deletes the database
```

Secrets are generated into `deploy/compose/.env` (git-ignored) on first run:
`SEED_ADMIN_PASSWORD` is the password for `admin@example.org` (and the demo accounts).

```text
postgres (healthy) ─► migrate (exit 0) ─┐
indexer: rag-index → volume `index` ───┴► api (healthy) ─► web :8080 (127.0.0.1 only)
networks: backend (internal: postgres, migrate, api) · frontend (api, web)
```

## Kubernetes

### Local (kind + Envoy Gateway)

Needs Docker, [kind](https://kind.sigs.k8s.io/) and kubectl.

```bash
scripts/k8s-up.sh            # cluster, Envoy Gateway, metrics-server, images, app → http://localhost:8088
scripts/k8s-verify.sh        # rolling restart + index rollout/rollback under k6 load: zero failed requests
scripts/k8s-status.sh
scripts/k8s-port-forward.sh  # fallback: http://localhost:8089 without the gateway
scripts/k8s-down.sh          # delete the cluster (--namespace-only keeps it)
E2E_BASE_URL=http://localhost:8088 E2E_PASSWORD=<SEED_ADMIN_PASSWORD> npm --prefix e2e test
```

`k8s-up` applies in two passes: everything except the API and the seed Job, then (after
`db-migrate` completes) the rest, so the API never starts on an old schema. It tags
`rag-api`/`rag-web` by image content, so re-running it rolls only what
changed. Credentials: `deploy/k8s/overlays/local/secrets.env` (git-ignored, generated).
Another cluster (k3d, minikube, k3s): `K8S_CONTEXT=<ctx> K8S_IMAGE_LOADER="<cmd reading
an image tar on stdin>" scripts/k8s-up.sh --existing-cluster`, with a Gateway API
implementation installed and its namespace labelled `healthcare-rag/gateway=true`.

### What runs

```text
             Gateway hcrag (Envoy) ── /api, /qa ──► Service api :8000 ──► api pods (HPA 2-6)
                    │                                    ▲                 init: rag-index → emptyDir
                    └──────── / ────► Service web :8080 ─┘ (nginx /api)   ──► postgres (StatefulSet, local)
Jobs: db-migrate (before rollout) · db-seed (local only)
```

| Object | Notes |
| --- | --- |
| Namespace `healthcare-rag` | Pod Security Standard **restricted** enforced |
| `api` Deployment | No `replicas` (the HPA owns it), `maxUnavailable: 0`, startup/readiness (`/readyz`: index + DB)/liveness probes, `preStop` sleep, topology spread, PDB `minAvailable: 1` |
| `web` Deployment | 2 replicas, same rollout settings, PDB |
| NetworkPolicies | default-deny ingress; gateway → web, api; web → api; api/migrate/seed → postgres |
| `db-migrate` Job | Runs before the rollout; Argo CD PreSync hook annotations |

### Operations

| Task | Command |
| --- | --- |
| Roll out a new index | `kubectl -n healthcare-rag set image deployment/api index=rag-index:<version>` |
| Roll back app or index | `kubectl -n healthcare-rag rollout undo deployment/api` (the index tag is part of the pod template) |
| History | `kubectl -n healthcare-rag rollout history deployment/api` |
| Which index is served | `curl http://localhost:8088/readyz` (`index_version`) |
| Restart without downtime | `kubectl -n healthcare-rag rollout restart deployment/api deployment/web` |
| Scrape metrics | add `components/service-monitor` (Prometheus Operator); label the monitoring namespace `healthcare-rag/monitoring=true` |

After an index rollout the dashboard's "active index" follows the deployment (audited as
`index.activate`, reason `deployment`). Activating, from the dashboard, a version whose
files are not in the running pods answers 409: roll the deployment instead.

### Production overlay

`deploy/k8s/overlays/prod`: managed PostgreSQL (`DATABASE_URL`) and `JWT_SECRET` from an
`ExternalSecret`, HTTPS on the Gateway with a cert-manager certificate and an HTTP→HTTPS
redirect, 3+ replicas, sign-in required, ServiceMonitor. Replace `rag.example.org` and
the image names. A `v*` release renders it with every image pinned by digest
(`healthcare-rag-<tag>.yaml` on the GitHub Release, [`docs/releasing.md`](../docs/releasing.md)).
`scripts/k8s-up.sh --overlay prod` only renders it to `artifacts/k8s-prod.yaml`.
