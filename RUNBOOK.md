# RUNBOOK: Healthcare Guidelines RAG Assistant

> ⚠️ This system ships with a **synthetic** guideline corpus and is **not for clinical use**.
> §4 lists what must be done before it serves real guidance.

Audience: the platform and on-call engineers who deploy and operate the service, and the
team that connects it to the organisation's guideline repository. Commands use Git Bash
syntax. Every script has a PowerShell twin (`scripts/<name>.ps1`, same flags).

| § | Contents |
| --- | --- |
| 1 | System at a glance |
| 2 | Environments |
| 3 | Deploy, upgrade, rollback: application and index separately |
| 4 | Swapping in a secure, real guideline repository |
| 5 | Retrieved text is data, not instructions |
| 6 | Operations: dashboards, alerts, logs, PHI, retention, backups |
| 7 | Scaling path |
| 8 | Release and maintenance checklist |
| 9 | Troubleshooting |

---

## 1. System at a glance

```text
 browser ──► Gateway (Envoy / any Gateway API impl.) ──► web  (nginx, SPA)      2+ pods
                         /api, /qa, /readyz … ───────► api  (FastAPI)         2–6 pods (HPA)
                                                         │  index: init container copies
                                                         │  rag-index:<version> → emptyDir
                                                         ▼
                                                   PostgreSQL (managed in prod)
```

| Component | State | Source of truth |
| --- | --- | --- |
| `api` | Stateless. The index is read-only in memory. Config is polled from the DB every `CONFIG_POLL_SECONDS` | Image `rag-api:<tag>` + ConfigMap `api-config` + Secret `hcrag-secrets` |
| Index | Immutable files, hash-verified at start (SC1) | Image `rag-index:<index_version>`, built from `corpus/` by CI |
| PostgreSQL | Users, refresh tokens, query log, reviews, escalations, eval runs, index versions, runtime config, audit log | Managed database (prod), StatefulSet (local) |
| `web` | Static | Image `rag-web:<tag>` |

Request path and decisions: [`docs/architecture.md`](docs/architecture.md). API:
[`docs/api.md`](docs/api.md). Release process: [`docs/releasing.md`](docs/releasing.md).

## 2. Environments

| Environment | Start | URL | Database | Index |
| --- | --- | --- | --- | --- |
| Local dev | `scripts/build-index.sh && scripts/seed.sh --demo && scripts/dev.sh` | :5173 (API :8000) | SQLite file | `artifacts/index` |
| Compose | `scripts/docker-up.sh [--demo] [--observability]` | :8080 | PostgreSQL container | `rag-index` image → volume |
| kind | `scripts/k8s-up.sh` | :8088 | PostgreSQL StatefulSet | init container |
| Production | GitOps or `kubectl apply -f healthcare-rag-<tag>.yaml` (release asset) | your host | Managed PostgreSQL | init container |

Production guards (`APP_ENV=production`): the API refuses to start with a weak
`JWT_SECRET`, `LOG_QUESTION_TEXT=true`, `CORS_ALLOW_ORIGINS=*`, or a demo seed. Every
setting is documented in [`.env.example`](.env.example).

## 3. Deploy, upgrade, rollback

The application (`rag-api`, `rag-web`) and the index (`rag-index`) are **separate
images with separate lifecycles**. A code release does not change answers unless it says
so. An index release changes answers and needs an evaluation (§3.4).

### 3.1 First production deploy

1. **Prerequisites:** Gateway API CRDs and an implementation; cert-manager with a
   `ClusterIssuer`; External Secrets Operator with a `ClusterSecretStore` named
   `platform-secrets`; managed PostgreSQL 16+; optional Prometheus Operator.
2. **Secrets** in the secret store: `healthcare-rag/database-url`
   (`postgresql+asyncpg://…?ssl=require`) and `healthcare-rag/jwt-secret`
   (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
3. **Overlay:** in `deploy/k8s/overlays/prod`, set the host name (`rag.example.org`) and
   the `ClusterIssuer`, and review replicas and resources.
4. **Apply** the release manifest (it is the prod overlay with images pinned by digest):

   ```bash
   kubectl apply -f healthcare-rag-v1.0.0.yaml           # from the GitHub Release
   kubectl -n healthcare-rag wait --for=condition=complete job/db-migrate --timeout=5m
   kubectl -n healthcare-rag rollout status deploy/api deploy/web --timeout=10m
   ```

   The `db-migrate` Job runs first (Argo CD PreSync hook, or `scripts/k8s-up.sh`'s
   two-pass apply). The API refuses to start on an unmigrated schema, so a missed
   migration fails loudly rather than corrupting data.
5. **Admin account:** run the seed once, then change the password. A demo seed is
   refused in production.

   ```bash
   kubectl -n healthcare-rag run seed --rm -it --restart=Never --image=<rag-api image> \
     --overrides='{"spec":{"containers":[{"name":"seed","image":"<rag-api image>","command":["python","scripts/seed.py"],"envFrom":[{"configMapRef":{"name":"api-config"}},{"secretRef":{"name":"hcrag-secrets"}}]}]}}'
   ```

6. **Verify:** `scripts/smoke.sh --base-url https://<host>` (probes, both `/qa` paths,
   schema), then sign in and open the dashboard. `/version` shows the build, contract and
   index versions.

### 3.2 Upgrade the application

1. Read the release notes (contract changes are additive within v1; ADR-0006).
2. Apply the new release manifest, or bump the image digests in GitOps. Order: the
   migration Job, then a rolling update (`maxUnavailable: 0`, readiness on `/readyz`,
   PDB `minAvailable: 1`). Verified with zero failed requests under load (Phase 9).
3. Watch: `kubectl -n healthcare-rag rollout status deploy/api`, the `RagServerErrors`
   and `RagQaLatencyHigh` alerts, then `scripts/smoke.sh --base-url …`.

**Migration policy: expand, then contract.** A migration that ships with release N must
keep release N−1 working (add columns and tables; never rename or drop in the same
release). Removals ship one release later. This is what makes §3.3 safe.

### 3.3 Roll back the application

```bash
kubectl -n healthcare-rag rollout undo deploy/api      # and/or deploy/web
# or re-apply the previous release's manifest (pinned digests): kubectl apply -f healthcare-rag-v0.9.0.yaml
```

Do **not** downgrade the database for an application rollback. With expand/contract the
old code runs on the new schema. `scripts/db-migrate.sh --downgrade <rev>` exists for
development; in production, restore from backup (§6.6) only if a migration damaged data.

### 3.4 Release a new index

Answers depend on the index, so an index change is a quality change, not a deployment
detail.

1. **Change the corpus** in a PR (`corpus/` or the source of §4). CI rebuilds the index,
   runs SC1 on Linux and Windows and the evaluation gate (dev pool, no regression against
   `backend/evaluation/baseline.json`).
2. **Evaluate:** `scripts/eval.sh --split dev`. If the corpus changed materially, also
   follow §4.7–4.9 (gold set, threshold, sign-off).
3. **Publish:** merging to `main` publishes `rag-index:<index_version>` to GHCR.
4. **Roll out** (the index tag is in the pod template, so this is an ordinary rollout):

   ```bash
   kubectl -n healthcare-rag set image deploy/api index=ghcr.io/<owner>/rag-index:<new_version>
   kubectl -n healthcare-rag rollout status deploy/api
   curl -s https://<host>/readyz          # "index_version": "<new_version>"
   ```

   Each pod copies the index into an `emptyDir` and verifies its hashes before reporting
   ready. During the rollout, old and new pods answer from their own index.
   `RagIndexVersionSplit` fires only if this lasts more than 15 minutes.
5. In GitOps, commit the new tag to the overlay instead of using `set image`.

### 3.5 Roll back an index

```bash
kubectl -n healthcare-rag rollout undo deploy/api              # previous pod template = previous index
kubectl -n healthcare-rag set image deploy/api index=ghcr.io/<owner>/rag-index:<old_version>   # explicit
```

Verified under load with zero failed requests (`scripts/k8s-verify.sh`).

**Dashboard activation** (Index & corpus → Activate) hot-swaps between versions that are
present **in the running pods** (the boot index and builds under `INDEX_STORE_DIR`; used
in Compose and dev). In Kubernetes the deployment decides. Activating a version whose
files are not in the pods returns **409**: roll the deployment instead (ADR-0015).

### 3.6 Configuration changes

| Kind | How | Takes effect |
| --- | --- | --- |
| Threshold, retrieval floor, confidence weights | Dashboard → Settings (admin). Versioned, with a reason, audited (`config.update`), and the impact preview comes from the last evaluation run | All pods within `CONFIG_POLL_SECONDS` (30 s) |
| Anything else (`.env.example` keys) | ConfigMap `api-config` / Secret, then `kubectl rollout restart deploy/api` | On restart |
| Settings that change `index_version` (`CHUNK_*`, `EMBEDDING_*`) | They are build inputs: change them in the index build, not in the API | New index (§3.4) |

Revert a runtime config by saving the previous values. The audit log has them (`before` /
`after`).

### 3.7 Compose equivalents

`scripts/docker-rebuild.sh` (application), `scripts/docker-up.sh` after an index change
(rebuilds `rag-index`), `scripts/docker-down.sh --volumes` (resets the database). Index
rollback in Compose: set `INDEX_IMAGE=rag-index:<old>` in `deploy/compose/.env` and
re-run `docker-up --no-build`.

---

## 4. Swapping in a secure, real guideline repository

The synthetic `corpus/` stands in for the organisation's guideline gateway. The pipeline
was built so the swap touches **one seam** (`DocumentSource`) plus configuration, while
parsing, chunking, hashing, the deterministic build, the validator and the API stay
unchanged. **The swap is not finished until §4.9 is signed off.** Until then
the deployment keeps the "not for clinical use" banner.

### 4.1 What changes, what does not

| Changes | Does not change |
| --- | --- |
| A `DocumentSource` adapter for the repository (§4.2) | Loader validation, chunker, embeddings, FAISS/BM25 build, `index_version` hashing |
| Credentials: workload identity for the build job (§4.3) | The API: it never talks to the repository |
| Conversion of source formats to Markdown + front-matter (§4.5) | `/qa` contract, validator, abstention policy |
| ACL metadata + retrieval-time filtering (§4.6), **required if any document is restricted** | Deployment, rollout and rollback (§3) |
| Gold set, threshold, sign-off (§4.7–4.9) | CI gates (they run on the new gold set) |

### 4.2 The `DocumentSource` contract

`backend/app/rag/ingestion/sources.py`:

```python
class DocumentSource(Protocol):
    @property
    def name(self) -> str: ...                    # for logs/errors; never a credential
    def files(self) -> Iterable[SourceFile]: ...  # SourceFile(path="<org>/<doc_id>.md", data=bytes)
```

Rules (enforced by `load_documents`; tests in `tests/unit/test_document_sources.py`):

- yield files in **ascending path order** (checked), with the same bytes for the same
  content;
- path `<org>/<doc_id>.md`; the folder must equal `source_org` and the file name the
  `doc_id` (checked);
- UTF-8 Markdown with the front-matter schema of `corpus/CORPUS_CARD.md` (checked: an
  invalid document fails the build, naming the file).

Adapter sketches. Each lists, fetches and converts **into a local snapshot**, and the
index is built from the snapshot (§4.4):

| Repository | Listing | Fetch | Notes |
| --- | --- | --- | --- |
| Internal document gateway (REST) | `GET /documents?status=published&since=…` with pagination | `GET /documents/{id}/content` | Prefer an export endpoint that returns a versioned bundle |
| AWS S3 / Azure Blob / GCS | `list_objects_v2` / `list_blobs` under a prefix, sorted by key | `get_object` / `download_blob` | Enable object versioning; record each version id in the snapshot manifest |
| SharePoint / OneDrive | Microsoft Graph `GET /sites/{site}/drives/{drive}/root/children` (or a delta query) | `GET /items/{id}/content` | Use an app registration with `Sites.Selected` scoped to the one site |

### 4.3 Authentication

- The **index build** reads the repository. The **API never does**: it only reads the
  built index image. Repository credentials therefore live only in the build job, never
  in the serving pods.
- Use **workload identity**, not static keys: EKS Pod Identity / IRSA, GKE Workload
  Identity, AKS Workload Identity, or GitHub Actions OIDC federation if CI builds the
  index. Grant **read-only** access, scoped to the guideline prefix, site or collection.
- Run the build as a Kubernetes Job (or CI job) in its own namespace and service
  account. Egress is limited to the repository endpoint (OI-38).
- Never log document content or credentials. The `name` of a source is a location, not a
  URL with a token.

### 4.4 Snapshot first, then build (determinism, SC1)

```text
repository ──fetch (job, workload identity)──► snapshot/  (+ snapshot.json: source ids, versions, ETags, fetched_at)
snapshot/ ──scripts/build-index.sh --corpus snapshot/──► index (index_version = hash of snapshot + build config)
```

A live repository changes under you. Building from a snapshot keeps an index reproducible
and auditable: keep the snapshot (or its versioned object ids) with the release, so
`verify-determinism` can rebuild the exact index later.

### 4.5 Converting source documents

Real guidelines arrive as PDF, DOCX or HTML. Convert them in the fetch step (for
example Docling or pandoc for DOCX/HTML; check the output of scanned PDFs page by page).
Then map the metadata:

| Front-matter field | Typical source |
| --- | --- |
| `doc_id` | Repository id, made stable and slug-safe (`who-ipc-004`) |
| `title`, `source_org`, `version`, `effective_date` | Document properties / catalogue record |
| `topic`, `audience`, `jurisdiction` | Catalogue tags (map to the controlled vocabulary in `CORPUS_CARD.md`) |
| `status`, `supersedes` | Lifecycle state. Superseded documents stay indexed but are flagged in answers (ADR-0010) |
| `synthetic` | `false` for real guidance |

Keep headings: the chunker uses H2 as a hard boundary and records `section_path` for
citations. Check a converted sample with `scripts/build-index.sh --inspect`.

### 4.6 Document-level access control and retrieval-time filtering

**Not implemented yet** (the synthetic corpus is public). It is **mandatory before any
restricted document is indexed**. Design:

1. **Metadata:** an `access` field in the front-matter, for example
   `access: {groups: ["icu-staff"], classification: internal}`. A missing field means
   `public` only if the source says so explicitly; otherwise the build fails (deny by
   default).
2. **Index:** store each chunk's allowed groups next to its row in `chunks.jsonl`. The
   ACL is part of the content hash, so a permission change creates a new
   `index_version`, which is auditable.
3. **Identity:** take the user's groups from the identity provider (OIDC claims, via the
   `AuthProvider` seam of ADR-0008; OI-24), never from the request body.
4. **Filter at retrieval, before ranking is cut to `top_k`:** over-fetch candidates
   (`RETRIEVAL_CANDIDATE_K`), drop every chunk the user may not read, then fuse, rank,
   extract and validate. A restricted chunk must never reach the answer, citations,
   snippets, the validator's score, the query log or the review queue. Filtering after
   generation is not enough: the validator would have used text the user cannot see.
5. **Everything downstream respects it:** reviewers see only what their own groups
   allow. Cached answers (if a cache is added) are keyed by ACL set. Metrics carry no
   content.
6. **Tests:** a per-role evaluation (the gold set run as each role must never cite a
   forbidden chunk), plus property tests that no response contains a chunk outside the
   caller's groups.

### 4.7 Re-annotating the gold set

The Phase 4 gold set describes the synthetic corpus, so it is meaningless for real
guidance. Follow `backend/evaluation/datasets/DATASET_CARD.md`:

- 150+ dev questions and a separate held-out test set, written by **clinicians or
  guideline owners** from real user questions (the query log's redacted questions and the
  review queue's promoted items are good seeds). Include about 15% unanswerable,
  near-domain questions.
- Label section-level, graded relevance (ADR-0001), **blind to system output**. A second
  annotator labels at least 20%; report agreement (Cohen's κ).
- `uv run --directory backend python -m evaluation.build_gold` regenerates the splits;
  `--check` keeps CI honest.

### 4.8 Re-tuning the threshold

1. Run `scripts/eval.sh --split dev` on the new index. The threshold sweep and the
   analyst list are in `backend/evaluation/reports/<run>/`.
2. Choose τ and the weights with the same rule as Phase 4 (`evaluation/threshold_sweep.py`):
   maximise the pass rate subject to **false validations ≤ 5%** on unanswerable
   questions, with 5-fold cross-validation on dev. For clinical use, consider ≤ 1%.
3. Freeze the configuration, then run the held-out split **once**:
   `scripts/eval.sh --split test`. A test split used for tuning is spent; write a new one.
4. Record the new numbers with `scripts/eval.sh --update-baseline` and in the evaluation
   report, then apply τ and weights in Settings (audited).

### 4.9 Validation sign-off checklist

| # | Check | Owner | Evidence |
| --- | --- | --- | --- |
| 1 | Source adapter yields the full intended collection; counts match the repository catalogue | Platform | Snapshot manifest |
| 2 | Determinism: `scripts/verify-determinism.sh --corpus snapshot/` passes on Linux and Windows | Platform | CI `determinism` jobs |
| 3 | No restricted document indexed without §4.6 ACL filtering in place and tested per role | Security | Per-role evaluation |
| 4 | Gold set written and double-annotated by clinicians (κ reported) | Clinical lead | DATASET_CARD |
| 5 | Held-out results: pass rate, P@5 / ceiling, **false validations ≤ the agreed limit**, with CIs | Clinical lead + ML | Evaluation report |
| 6 | Error analysis of every false validation and a sample of abstentions reviewed by a clinician | Clinical lead | Analyst list |
| 7 | Superseded documents flagged correctly in answers | Clinical lead | Spot check |
| 8 | PHI controls verified in the target environment (§6.4); `LOG_QUESTION_TEXT=false` | Privacy | §6.4 log check |
| 9 | Alerts routed to an on-call rotation; this runbook reviewed by it | Operations | Alertmanager config |
| 10 | Clinical governance approval of the intended use; disclaimer text updated | Governance | Approval record |

---

## 5. Retrieved text is data, not instructions

The default generator is **extractive**: it copies sentences from retrieved chunks and
cannot follow instructions in them. Prompt injection has no effect on the answer path. The
risks appear if the optional LLM generator (`GENERATOR=llm`, off by default) is enabled, or
if a future agent uses retrieved text:

- Treat every retrieved chunk as **untrusted data**. Put it in a clearly delimited data
  section of the prompt, and instruct the model that content inside it is quotation, never
  instruction.
- **Validation still decides.** An LLM answer goes through the same validator: coverage
  against the cited text, query support, retrieval score and the numeric gate. Text the
  model invents, including text an injected instruction asked for, does not appear in
  the citations and lowers coverage, so the answer is withheld.
- Give the generator **no tools** and no network access. It returns text only, so an
  injected "call this URL" has nothing to call.
- Scan the corpus at ingestion for instruction-like patterns ("ignore previous
  instructions", hidden HTML, zero-width characters) and route matches to human review.
  Strip HTML comments and invisible characters in conversion (§4.5).
- Write access to the guideline repository is a security boundary: whoever can edit a
  guideline can influence answers. Protect it like code (review, audit, signed releases).
- Log requests, citations and validator signals (not raw prompts with PHI), so a
  suspicious answer can be traced to the chunk that caused it.

---

## 6. Operations

### 6.1 Dashboards and metrics

Prometheus scrapes `api:8000/metrics` (Compose: `docker-up --observability`, Grafana on
:3000 with the provisioned *Healthcare RAG* dashboard; Kubernetes: the
`service-monitor` component, which also installs the alert rules).

| Metric | Type | Meaning |
| --- | --- | --- |
| `qa_requests_total{status}` | counter | Answers, by `validated` / `needs_review` |
| `qa_abstentions_total{reason}` | counter | `no_evidence`, `below_retrieval_floor`, `numeric_mismatch`, `low_confidence` |
| `qa_confidence` | histogram | Confidence distribution |
| `qa_latency_seconds` | histogram | QA pipeline latency |
| `http_requests_total{method,route,status_code}`, `http_request_duration_seconds` | counter, histogram | HTTP traffic |
| `qa_log_dropped_total` | counter | Query-log rows lost (queue full or DB error) |
| `rag_index_info{index_version}` | gauge | The index each pod serves |

### 6.2 Alerts

Rules: `deploy/compose/observability/alerts.yml` (same groups as the Kubernetes
`PrometheusRule`; unit-tested with `promtool test rules`). `page` = act now; `ticket` = same
working day.

#### RagApiDown

*page*: Prometheus cannot scrape the API for 2 minutes.
1. `kubectl -n healthcare-rag get pods -l app.kubernetes.io/component=api`. Look for
   CrashLoopBackOff, Pending or OOMKilled.
2. `kubectl -n healthcare-rag logs deploy/api --previous | tail -50`. Usual causes:
   schema not migrated (run the `db-migrate` Job), index hash mismatch (init container
   failed: re-pull the index image), production guard (weak secret, question logging on).
3. If a new release caused it: §3.3.

#### RagNotReady

*page*: `/readyz` answers 503 for 5 minutes. Pods are up but not taking traffic.
1. `curl -s https://<host>/readyz`. `checks.database` or `checks.index` names the part.
2. Database: check the managed DB status, connection limits and `DATABASE_URL` secret
   rotation (ExternalSecret refresh).
3. Index: the init container logs show the copy. A manifest/hash mismatch means a
   corrupted or wrong image: roll back (§3.5).

#### RagAbstentionSpike

*ticket*: more than 50% of answers withheld for 15 minutes.
1. Dashboard → Overview → *Why answers were withheld*, and
   `qa_abstentions_total` by `reason`.
2. Correlate with changes: a recent **index rollout** (§3.4; roll back if the new index
   regressed), a **settings change** (audit log `config.update`; revert), or a change
   in traffic (new users asking out-of-scope questions; check the review queue and Query
   explorer). The last case is information, not an incident.
3. `below_retrieval_floor` dominating: the questions are outside the corpus.
   `low_confidence` dominating with normal questions: run `scripts/eval.sh --split dev`
   against the live configuration.

#### RagQaLatencyHigh

*ticket*: `/qa` p95 above 300 ms for 10 minutes (Phase 7 load gate: 179 ms at 50 VUs).
1. CPU saturation? `kubectl top pods`. The HPA scales at 70% CPU to 6 pods; raise
   `maxReplicas` or the CPU limit.
2. A much larger index? See §7.
3. Database slowness reaches `/qa` only through the asynchronous query-log writer, which
   drops rows rather than block (watch `RagQueryLogDropped`).

#### RagServerErrors

*page*: more than 1% of HTTP responses are 5xx for 5 minutes.
1. Logs: `http.unhandled_exception` events (with `request_id`; §6.3).
2. 503s from every route usually mean the database is unreachable: pods then also fail
   readiness, so `RagNotReady` fires too. Fix the database first.
3. A new release caused it: §3.3.

#### RagQueryLogDropped

*ticket*: query-log rows were dropped. The audit trail of questions has a gap.
1. Database errors in the logs (`qa.query_log_dropped`), or sustained traffic above the
   writer's capacity (`QUERY_LOG_QUEUE_SIZE`, default 10,000).
2. Fix the database and record the gap (time window) for the audit record.

#### RagIndexVersionSplit

*ticket*: pods have served different index versions for more than 15 minutes.
1. `kubectl -n healthcare-rag get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.initContainers[0].image}{"\n"}{end}'`
2. A stuck rollout (`kubectl rollout status deploy/api`): fix or `rollout undo`.
3. In Compose/dev: an admin activated a version on one process only. Activate the
   intended version again.

### 6.3 Logs

JSON in production (`LOG_FORMAT=json`), one object per event, with `request_id` (also
the `X-Request-ID` response header and the `request_id` in every error body).

| Event | Key fields |
| --- | --- |
| `http.request` | `method`, `route`, `status_code`, `duration_ms` |
| `qa.completed` | `status`, `reason`, `confidence`, `top_k`, `latency_ms`, `index_version`, `citations` (chunk ids), `signals`, `unsupported_numbers`; `question` only when `LOG_QUESTION_TEXT=true` (never in production) |
| `index.activated`, `config.applied`, `eval.succeeded`, `retention.purged`, `qa.query_log_dropped`, `http.unhandled_exception` | as named |

```bash
# One request, end to end (a user reports a request id from an error message)
kubectl -n healthcare-rag logs -l app.kubernetes.io/component=api --since=1h | jq -c 'select(.request_id=="<id>")'
# Abstentions by reason in the last hour
kubectl -n healthcare-rag logs -l app.kubernetes.io/component=api --since=1h \
  | jq -r 'select(.event=="qa.completed" and .status=="needs_review") | .reason' | sort | uniq -c
# Loki (LogQL)
sum by (reason) (count_over_time({namespace="healthcare-rag"} | json | event="qa.completed" | status="needs_review" [1h]))
```

The query log in the database holds the **redacted** question (Dashboard → Query
explorer). It is the place to investigate content; logs are for operations.

### 6.4 PHI redaction: how to verify it

Users can type patient details into a question, even though the UI warns against it
(ADR-0009). Before persistence, `app/core/redaction.py` replaces e-mail addresses,
record numbers (MRN, NHS, patient id, SSN), dates of birth and dates, phone numbers,
titled or "patient …" names, and long digit runs with placeholders. Verify in each new
environment:

1. `LOG_QUESTION_TEXT=false` (the API refuses to start in production otherwise).
2. Ask: *"Patient John Smith, MRN 12345678, born 03/04/1961, phone 555-123-4567: when
   should gloves be worn?"*
3. Dashboard → Query explorer: the stored question reads `[NAME], [ID], [DATE], phone
   [PHONE]: when should gloves be worn?` and `redactions` > 0.
4. `kubectl logs … | grep -c "John Smith"` returns 0.
5. The rules are tested in `backend/tests/unit/test_redaction.py`. Rule-based redaction
   is a safety net, not a guarantee (free-text names without a title are not caught).
   Retention (§6.5) limits exposure.

### 6.5 Retention

Query-log rows older than `QUERY_LOG_RETENTION_DAYS` (default 30) and expired refresh
tokens are purged every `RETENTION_PURGE_INTERVAL_MINUTES` by the API (`retention.purged`
event, audited). On demand:
`kubectl -n healthcare-rag exec deploy/api -- python scripts/maintenance.py purge --retention-days 30`.
Reviews keep the redacted question they reference. Audit-log retention follows the
organisation's records policy (no automatic purge).

### 6.6 Backups

- **Database:** managed point-in-time recovery (≥ 7 days) plus a daily logical backup
  (`pg_dump -Fc`) to a separate account. Test a restore quarterly into a scratch
  database, then run `scripts/db-migrate.sh --current` against it.
- **Index:** nothing to back up. Every version is an immutable image in GHCR, rebuildable
  byte-for-byte from git (`scripts/verify-determinism.sh`).
- **Releases:** the GitHub Release keeps the manifest, SBOMs and demo for each version.

### 6.7 Routine tasks

| When | Task |
| --- | --- |
| Daily | Review queue: withheld and escalated answers (reviewer role) |
| Weekly | Dashboard → Evaluation → *Run evaluation*. Compare with the baseline; read the low-confidence list |
| Weekly | Dependabot PRs (CI gates them; regenerate `THIRD_PARTY_NOTICES.md` if runtime dependencies changed, §8) |
| Per release | §8 checklist |

---

## 7. Scaling path

The index is `IndexFlatIP` (exact cosine, 256-D float32) plus BM25 in memory (ADR-0005).

| Corpus | Chunks | Index memory | Retrieval | Action |
| --- | --- | --- | --- | --- |
| Today | 346 | < 1 MB | < 1 ms | none |
| One organisation's guidelines | 10⁴–10⁵ | 10–100 MB | ~1–10 ms (exact) | none; keep exact search |
| Several organisations, archives | 10⁶ | ~1 GB vectors + BM25 | flat search ~100 ms per query | move to IVF-Flat or HNSW (FAISS), pinned `nprobe`/`efSearch` |
| Larger, multi-tenant, frequent updates | 10⁷+ | — | — | external vector store (pgvector, Qdrant, OpenSearch) behind the `VectorStore` protocol |

Move when **measured** p95 retrieval time or pod memory approaches the budget (the
`RagQaLatencyHigh` alert, `kubectl top`), not before. When moving:

- **Recall:** approximate search loses some neighbours. Measure Recall@5 against exact
  search on the dev pool and require ≥ 0.98, then re-run the evaluation.
- **Determinism (SC1):** IVF training uses k-means; fix the seed and training sample and
  confirm byte-identical rebuilds. HNSW construction order must be fixed. If it cannot be
  made reproducible, version the index by content plus build log.
- **BM25:** at 10⁶+ chunks, move sparse retrieval to the same engine (OpenSearch,
  Qdrant sparse vectors) to keep one source of truth.
- The dense vector currently ranks nothing (`RRF_WEIGHT_DENSE=0`; evaluation report
  §3.2). A real semantic embedder would change that and is the bigger quality lever.

Horizontal scaling of the API is already in place (stateless pods, HPA 2–6). Database
load is light: one asynchronous insert per question.

---

## 8. Release and maintenance checklist

- [ ] CI green on `main` (`ci-passed`), including the evaluation gate and the image scan
- [ ] `uv run --directory backend python scripts/third_party_notices.py --check` (regenerate if runtime dependencies changed)
- [ ] Contract changes are additive; `backend/openapi.json` and the frontend types regenerated (`scripts/gen-client.sh`)
- [ ] Migrations follow expand/contract (§3.2)
- [ ] Index changes: evaluation run and recorded (§3.4)
- [ ] `scripts/reproduce.sh` passes (numbers equal their records)
- [ ] Tag `vX.Y.Z` → release workflow: images promoted, manifest pinned by digest, SBOMs, demo video (docs/releasing.md)
- [ ] Release notes mention answer-affecting changes (index, threshold, weights)

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| API exits at start: "schema is at …" | Migrations not applied | Run the `db-migrate` Job / `scripts/db-migrate.sh` |
| API exits at start: "index … does not match its manifest" | Corrupted or mixed index files | Re-pull the index image; locally `scripts/build-index.sh` |
| Every question `below_retrieval_floor` | Wrong or empty index mounted | `/readyz` → `index_version`; compare with the expected release |
| Admin and auth routes 503, `/qa` works | `DATABASE_URL` empty (stateless mode, by design) | Set `DATABASE_URL` and run the migrations |
| Pods not ready, `/readyz` shows `"database": "fail"` | Database unreachable | Fix the database or the `DATABASE_URL` secret (`RagNotReady`) |
| 401 on `/qa` | `ALLOW_ANONYMOUS_QA=false` (production default) | Sign in; the SPA sends the bearer token |
| 429 | Per-pod rate limit (`RATE_LIMIT_QA`) | Expected under abuse. Limits are per pod (OI-11) |
| 409 activating an index in the dashboard | Version not present in the pods | Roll the deployment (§3.4) |
| Windows: index hash differs from CI | CRLF checkout of `corpus/` | `.gitattributes` forces LF; run `git add --renormalize .` and re-check |
| `demo-record`: "no libx264" | ffmpeg without H.264 | `winget install Gyan.FFmpeg` |
