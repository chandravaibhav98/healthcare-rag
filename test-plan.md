Each check has an ID (e.g. `P3-04`) so you can log results in the template at the end. Commands are in Git Bash syntax and run from the repo root unless a step says `cd backend`. Do them in order: each phase builds on the one before.

---

## Shared setup (do this once)

```bash
# Optional but makes every check below easier to read
winget install jqlang.jq

cp -n .env.example .env          # dev defaults: SQLite DB, anonymous /qa allowed
export API=http://localhost:8000

# Helper: ask a question (arguments: question, then top_k, default 5)
q() { curl -s -X POST "$API/api/v1/qa" -H 'Content-Type: application/json' \
      -d "{\"question\":\"$1\",\"top_k\":${2:-5}}"; }
```

**Dev accounts:**

- From `scripts/seed.sh --demo`: `admin@example.org`, `reviewer@example.org` and `user@example.org`, all using `SEED_ADMIN_PASSWORD` (`change-me-admin` by default).
- From the Playwright self-started stack: the same emails with password `e2e-password-123`.

---

## Phase 0 — Foundations, Contracts & Decisions

| ID | Do | Pass if |
| --- | --- | --- |
| P0-01 | `scripts/setup.sh --help`, then `scripts/setup.sh` | Help prints flags. Setup finishes with exit code `0` (`echo $?`) |
| P0-02 | Run `scripts/setup.sh` a second time | Still `0`, and nothing is duplicated (it's idempotent) |
| P0-03 | `scripts/preflight.sh --strict` | Every prerequisite shows green, and missing tools are named clearly |
| P0-04 | `scripts/lint.sh` | ruff, mypy, eslint, prettier and tsc are all clean |
| P0-05 | `git ls-files --eol corpus \| grep -c crlf` | `0` (this matters for determinism) |
| P0-06 | Add a line `aws_secret_access_key = AKIAIOSFODNN7EXAMPLE` to any file, then `git add` it and `git commit` | The pre-commit secret scan **blocks** the commit. Then run `git restore --staged . && git checkout -- .` <!-- pragma: allowlist secret -->
| P0-07 | Add `FOO_BAR=1` to `.env.example`, then `cd backend && uv run pytest tests/unit/test_config.py` | The test **fails** because config drifted. Revert the line afterwards |
| P0-08 | `scripts/gen-client.sh --check` | Says the generated TS client matches `backend/openapi.json` |
| P0-09 | Read ADR-0001 and ADR-0002 in `docs/adr/` | Each has Status, Context, Decision and Consequences, and the numbers match `.env.example` (weights 0.20/0.60/0.20, τ 0.6) |

---

## Phase 1 — Synthetic Corpus & Deterministic Indexing (SC1)

| ID | Do | Pass if |
| --- | --- | --- |
| P1-01 | `ls corpus/*/*.md \| wc -l` | About 72 documents, roughly equal across WHO, NIH and CDC |
| P1-02 | Open 3 random corpus files | Front-matter has `doc_id, title, source_org, version, effective_date, topic, synthetic: true` |
| P1-03 | `scripts/build-index.sh` | `artifacts/index/` contains `index.faiss, bm25.json, chunks.jsonl, embedder.json, manifest.json` |
| P1-04 | `sha256sum artifacts/index/* > /tmp/h1`, run `scripts/build-index.sh` again, then `sha256sum artifacts/index/* \| diff /tmp/h1 -` | **No diff** (byte-identical rebuild) |
| P1-05 | `scripts/verify-determinism.sh --runs 3` | Reports identical hashes across all runs |
| P1-06 | `cd backend && PYTHONHASHSEED=1 uv run python scripts/pipeline.py build --out /tmp/a && PYTHONHASHSEED=999 uv run python scripts/pipeline.py build --out /tmp/b && diff <(cd /tmp/a && sha256sum *) <(cd /tmp/b && sha256sum *)` | No diff, so Python's hash salt doesn't leak into the index |
| P1-07 | `uv run python scripts/pipeline.py inspect --stats` | Chunk counts look sensible, and no document has 0 chunks |
| P1-08 | `uv run python scripts/pipeline.py inspect --doc who-ppe-001 --limit 20` | Chunks follow the headings (`section_path` set), and no numbered procedure or table is cut mid-step |
| P1-09 | **Negative test:** add one space to a corpus file, then `uv run python scripts/pipeline.py verify` | Reports the index as **stale or mismatched**. Revert the file and re-verify to get a clean result |
| P1-10 | Compare `index_version` in `manifest.json` before and after changing `EMBEDDING_HASH_SALT` in `.env` | The version changes. Revert the salt |

---

## Phase 2 — Retrieval & Extractive QA Core

Run these from `backend/`, using `uv run python scripts/pipeline.py ask "<question>" [--mode dense|sparse|hybrid] [--no-expansion]`.

| ID | Question / action | Pass if |
| --- | --- | --- |
| P2-01 | `"When should health workers perform hand hygiene?"` | A hand-hygiene document is top-1, and the answer has 1–3 sentences with `[n]` markers |
| P2-02 | `"What PPE is required for airborne precautions?"` | A PPE or transmission-based-precautions document is in the top 5 |
| P2-03 | `"IPC measures for sterilisation"` with and without `--no-expansion` | With expansion, the ranking is the same or better (acronym mapping works) |
| P2-04 | The same question in `--mode sparse`, `dense` and `hybrid` | Hybrid ≥ sparse. Dense is weaker, which is expected (ADR-0011 sets the dense weight to 0) |
| P2-05 | Every `[n]` in any answer | Resolves to a listed citation. No `[4]` appears when only 3 citations exist |
| P2-06 | A question touching two versions of a PPE guideline (e.g. glove change guidance) | The current version is cited and the superseded one isn't used as answer text (ADR-0010) |
| P2-07 | A sentence containing "e.g." or "approx." in the source | The answer doesn't break the sentence at the abbreviation |
| P2-08 | Run P2-01 twice | Identical output (deterministic ordering) |

**Smoke gate:** `uv run pytest tests/integration/test_retrieval_smoke.py -v` must pass (the expected document appears in the top 5 for at least 9 of 10 questions).

---

## Phase 3 — Validation, Confidence & the `/qa` API (SC4, D1)

Start the API with `scripts/dev.sh --api-only`, then:

| ID | Do | Pass if |
| --- | --- | --- |
| P3-01 | `curl -s $API/healthz; curl -s $API/readyz; curl -s $API/version` | All return 200. `readyz` shows the index is loaded |
| P3-02 | `q "When should health workers perform hand hygiene?" \| jq` | Top-level keys are **exactly** `answer, citations, confidence, status`, plus `meta`. `status: "validated"` and `confidence ≥ 0.6` |
| P3-03 | From the P3-02 result, check `meta.signals` | `coverage, query_support, retrieval_score` are all in [0, 1], and `numeric_ok` is a boolean |
| P3-04 | `q "What is the capital of France?" \| jq` | `status: "needs_review"`, the answer is the **standard abstention text**, `meta.reason` says below the floor, and no clinical text is shown |
| P3-05 | `q "What temperature range should vaccines be stored at?" \| jq` | Every number in `answer` appears in a cited `snippet` (open the citation to check). `numeric_ok: true` |
| P3-06 | Compare `curl -s -X POST $API/qa -H 'Content-Type: application/json' -d '{"question":"hand hygiene moments"}'` with the `/api/v1/qa` result | The alias response is identical apart from `request_id` and `latency_ms` |
| P3-07 | `q "hi"`, `q "hand hygiene" 0`, `q "hand hygiene" 21` | **422** with `Content-Type: application/problem+json` (check with `curl -i`) |
| P3-08 | `-d '{"question":"x","foo":1}'` and `-d 'not json'` | 422 problem+json, with no stack trace in the body |
| P3-09 | `curl -i -X GET $API/api/v1/qa` | 405 |
| P3-10 | `curl -i -H 'X-Request-ID: test-abc-123' ...` | The response echoes `x-request-id: test-abc-123`, and `meta.request_id` matches |
| P3-11 | `for i in $(seq 70); do q "hand hygiene" >/dev/null; done; curl -i ...` | A 429 appears after about 60 requests per minute |
| P3-12 | `curl -s $API/metrics \| grep qa_` | `qa_requests_total{status=...}`, the confidence histogram, latency and abstentions are present |
| P3-13 | Delete one byte from `artifacts/index/chunks.jsonl` (keep a backup), then restart the API | Startup **fails fast** with a manifest hash error. Restore the file |
| P3-14 | Open `http://localhost:8000/docs` | Both routes appear, with the clinical disclaimer in the description |
| P3-15 | `scripts/smoke.sh --bench` | p95 under 150 ms locally |

---

## Phase 4 — Evaluation & Threshold Tuning (SC2, SC3) 🏁 M1

| ID | Do | Pass if |
| --- | --- | --- |
| P4-01 | `scripts/eval.sh --split dev` then `scripts/eval.sh --split test` | A run folder appears under `backend/evaluation/reports/` with `metrics.json`, `per_query.csv`, `low_confidence.csv` and an SVG plot |
| P4-02 | `jq . backend/evaluation/reports/<test-run>/metrics.json` | **P@5 ≥ 0.65**, **pass rate ≥ 0.80** (answerable test questions), false-validation ≤ 5% |
| P4-03 | Compare with `docs/evaluation-report.md` | The numbers match the committed report exactly, so they're reproducible |
| P4-04 | **The most valuable manual check:** pick 10 random rows of `per_query.csv` (5 validated, 5 needs_review) and read the cited corpus passage yourself | Validated answers are genuinely correct. Abstentions are genuinely weak or out of scope. Note any disagreement |
| P4-05 | Read 5 gold items in `gold_test.jsonl` | The relevant chunk IDs really answer the question (ADR-0001 section-level definition) |
| P4-06 | Set `CONFIDENCE_THRESHOLD=0.9` in `.env`, restart, and re-run P3-02 | The status flips to `needs_review` more often. Revert to 0.6 |
| P4-07 | `cd backend && uv run pytest tests/regression -v` | Quality gates pass |
| P4-08 | Check the threshold-sweep SVG in `docs/evaluation/` | Pass rate and false-validation curves are visible, and the chosen τ is justified in the report |

---

## Phase 5 — Persistence, Auth & Admin APIs

```bash
scripts/db-migrate.sh && scripts/seed.sh --demo
login() { curl -s -c /tmp/ck -X POST $API/api/v1/auth/login -H 'Content-Type: application/json' \
          -d "{\"email\":\"$1@example.org\",\"password\":\"change-me-admin\"}"; }
login admin | jq     # copy the access token into ADM; repeat for reviewer → REV, user → USR
H() { echo "Authorization: Bearer $1"; }
```

| ID | Do | Pass if |
| --- | --- | --- |
| P5-01 | `scripts/db-migrate.sh --current` | Shows the head revision |
| P5-02 | `curl -s -H "$(H $ADM)" $API/api/v1/auth/me` | Returns the admin role |
| P5-03 | **RBAC matrix:** call `GET /api/v1/admin/stats`, `/admin/reviews` and `PUT /admin/config` with no token, `USR`, `REV` and `ADM` | No token gives 401. User gives 403 on all three. Reviewer gets 200 on stats and reviews but 403 on config. Admin gets 200 on all |
| P5-04 | `GET /admin/queries?status=needs_review` | Paginated, filtered results containing the demo history |
| P5-05 | `GET /admin/config` (note `version`), then `PUT` with `expected_version`, a new threshold and a `comment` | 200, and the version increments |
| P5-06 | Repeat P5-05 with the **old** `expected_version` | 409 (the optimistic lock works) |
| P5-07 | `GET /admin/audit-log` | The config change appears with the actor, timestamp and your comment |
| P5-08 | **PHI:** `q "Patient john.doe@mail.com 555-123-4567 MRN 12345678 needs PPE advice"`, then find it in `/admin/queries` | Email, phone and MRN are **redacted** in storage |
| P5-09 | Send 11 bad logins within a minute | 429 on login |
| P5-10 | `curl -b /tmp/ck -X POST $API/api/v1/auth/refresh`, then `/logout`, then refresh again | Refresh works, then fails after logout |
| P5-11 | `GET /admin/reviews/export/gold.jsonl` after a reviewer "correct" verdict | That item appears in valid gold-schema JSONL |
| P5-12 | `GET /admin/index/versions`, then activate another version | The active flag moves, `/readyz` and `meta.index_version` change, and an audit entry is written |
| P5-13 | Set `DATABASE_URL=` (empty) and restart | `/qa` still works. Auth and admin routes return **503** (stateless mode). Restore the setting |

Reviewer verdicts are easiest to submit from `/docs` using the "Authorize" button. That also checks that the OpenAPI auth setup works.

---

## Phase 6 — React Frontend (Assistant and Admin Dashboard)

Run `scripts/dev.sh` and open `http://localhost:5173`.

**Query Assistant**

- [ ] P6-01: A clinical disclaimer banner is visible on every page.
- [ ] P6-02: Ask the P3-02 question. You see a **validated** badge, a confidence meter, and a tooltip showing the 3 signals. The `[n]` chips are clickable.
- [ ] P6-03: Click a citation. The evidence panel shows the source with **overlapping tokens highlighted** and numbers marked as checked.
- [ ] P6-04: Ask the P3-04 question. You see the **needs-review** state, candidate sources, and an "Escalate" action. After escalating, the item appears in the Review Queue as admin.
- [ ] P6-05: Check the empty state, loading state, and error state. For the error state, stop the API mid-session: you should get a friendly message, not a blank screen.
- [ ] P6-06: Session history works, and "copy answer" includes the citations.

**Admin (log in as each role)**

- [ ] P6-07: **User:** the dashboard link is hidden, and going directly to `/admin` shows the 403 page.
- [ ] P6-08: **Reviewer:** sees Overview, Review Queue, Queries and Evaluation, but not Settings, Index or Audit.
- [ ] P6-09: **Admin:** all sections. The Overview KPIs roughly match `/admin/stats`.
- [ ] P6-10: Review Queue: approve, reject and correct an item, and promote one to gold.
- [ ] P6-11: Settings: the threshold editor shows an impact preview, and saving creates an Audit Log row.
- [ ] P6-12: Evaluation: "Run evaluation" completes and adds a row to the history.

**Quality**

- [ ] P6-13: Use the whole app **keyboard-only** (Tab, Enter, Esc). Focus is always visible, and drawers trap and release focus.
- [ ] P6-14: Toggle dark mode, and resize to 375 px and 1920 px widths. Nothing overlaps.
- [ ] P6-15: Run DevTools → Lighthouse → Accessibility on `/` and `/admin`. Both should score 95 or higher. Also run `npm --prefix e2e run audit`.

---

## Phase 7 — Test Hardening & Quality Gates

| ID | Do | Pass if |
| --- | --- | --- |
| P7-01 | `scripts/test.sh --all --coverage` | All green. Coverage meets rag ≥90%, services ≥85%, backend ≥80% and frontend ≥70% |
| P7-02 | `npm --prefix e2e test`, then `npm --prefix e2e run report` | All 4 specs pass, and the HTML report opens |
| P7-03 | `scripts/load-test.sh --vus 50 --duration 5m` (raise `RATE_LIMIT_QA` first, as `.env` notes) | p95 under 300 ms and 0% 5xx |
| P7-04 | `scripts/security-scan.sh` | No criticals, and gitleaks is clean |
| P7-05 | **Test the tests:** temporarily make `coverage()` in `backend/app/rag/validation/coverage.py` always `return 1.0`, then run `scripts/test.sh --backend` | Unit, property **and** regression tests **fail**. Revert with `git checkout -- backend/app/rag/validation/coverage.py` |
| P7-06 | Temporarily rename a field in `app/api/schemas/qa.py`, then run `uv run pytest tests/contract` | The OpenAPI snapshot test **fails**. Revert the change |

P7-05 and P7-06 are worth showing a reviewer: they show the tests actually catch regressions, not just that they pass.

---

## Phase 8 — Docker & Compose

| ID | Do | Pass if |
| --- | --- | --- |
| P8-01 | `scripts/docker-up.sh --demo` | Built, migrated, indexed and seeded, and the smoke test passes. The URL and password location are printed |
| P8-02 | `docker compose -f deploy/compose/docker-compose.yml ps` | postgres, api and web are **healthy**. migrate and indexer show **exited (0)** |
| P8-03 | Open `http://localhost:8080` and log in as admin using `SEED_ADMIN_PASSWORD` from `deploy/compose/.env` | Works the same as dev mode, with no CORS errors in the console |
| P8-04 | `docker compose ... exec api id -u` | Not `0` (non-root) |
| P8-05 | `docker images \| grep rag-` | API image under about 400 MB |
| P8-06 | Compare `index_version` from the indexer container's manifest (`docker compose ... logs indexer`) with your local `artifacts/index/manifest.json` | Same hash, so the index is deterministic inside the container too |
| P8-07 | `curl -I http://localhost:8080` | CSP and security headers are present |
| P8-08 | `docker compose ... restart api` while using the UI | Recovers on its own, and the web container doesn't crash |
| P8-09 | `scripts/docker-down.sh`, then `docker-up.sh --no-build` | Data persists (the volume is kept) |
| P8-10 | `scripts/docker-down.sh --volumes` | Clean teardown |
| P8-11 | `scripts/docker-up.sh --demo --observability` | Prometheus (`:9090`) targets show **UP**, and the Grafana (`:3000`) RAG dashboard shows data after a few queries |

---

## Phase 9 — Kubernetes (kind)

| ID | Do | Pass if |
| --- | --- | --- |
| P9-01 | `scripts/k8s-up.sh --recreate` | Cluster created, images loaded, rollout complete, smoke test passes at `http://localhost:8088` |
| P9-02 | `scripts/k8s-status.sh` | API has 2/2 replicas Ready. HPA, PDB and NetworkPolicies are listed |
| P9-03 | `kubectl get ns`, then `kubectl -n <ns> describe pod <api-pod>` | Init container copied the index. Probes are configured. `runAsNonRoot` and `readOnlyRootFilesystem` are set |
| P9-04 | `kubectl -n <ns> delete pod <one-api-pod>` while refreshing the UI | No failed requests (the other replica serves), and the pod is replaced |
| P9-05 | **NetworkPolicy:** `kubectl -n <ns> run probe --rm -it --image=curlimages/curl -- curl -m 3 http://<postgres-svc>:5432` | **Times out or is blocked** |
| P9-06 | `scripts/k8s-verify.sh` | Rolling restart under k6 load gives 0 failures, and the index rollout and rollback both pass |
| P9-07 | `kubectl -n <ns> rollout undo deploy/<api>` | `meta.index_version` returns to the previous value |
| P9-08 | `E2E_BASE_URL=http://localhost:8088 E2E_PASSWORD=<from deploy/k8s/overlays/local/secrets.env> npm --prefix e2e test` | E2E is green against the cluster |
| P9-09 | `kubectl kustomize deploy/k8s/overlays/prod \| less` | Renders without error, with a managed DB secret reference, TLS and larger resource limits |
| P9-10 | `scripts/k8s-down.sh` | Cluster removed |

---

## Phase 10 — CI/CD

| ID | Do | Pass if |
| --- | --- | --- |
| P10-01 | Push a branch and open a PR | Every job runs: lint, typecheck, unit, integration, contract, determinism (including the Windows job), eval-gate, frontend, image build, trivy, kind and E2E |
| P10-02 | On a throwaway branch, set `RRF_WEIGHT_SPARSE=0.0` in `.env.example` and the matching default, then push | The **eval-gate fails**, and the PR can't be merged |
| P10-03 | Try `git push origin main` directly | **Rejected** by the ruleset. Also run `scripts/github-protect.sh --dry-run` |
| P10-04 | Check the PR artifacts | The evaluation report and Playwright HTML report can be downloaded |
| P10-05 | After the merge to main | Images appear in GHCR tagged with the git SHA and `index_version`, and an SBOM is attached |
| P10-06 | Push a `v*` tag | The release workflow publishes release notes and the rendered prod manifests |

---

## Phase 11 — Playwright Demo Video

| ID | Do | Pass if |
| --- | --- | --- |
| P11-01 | `scripts/demo-record.sh --gif` | Produces `artifacts/demo/healthcare-rag-demo-<UTC>.mp4`, a GIF and `demo-chapters.txt` |
| P11-02 | Watch the MP4 | All 10 chapters play in order, captions are readable, and there are no hidden error toasts or spinners |
| P11-03 | Record twice and compare | The same content and flow both times |
| P11-04 | Open the MP4 in a plain player (e.g. Windows Media Player) | Plays as H.264 at 1920×1080 |

---

## Phase 12 — Docs & Submission

| ID | Do | Pass if |
| --- | --- | --- |
| P12-01 | `git clone <repo> /c/tmp/fresh && cd /c/tmp/fresh && scripts/reproduce.sh --quick` | Metrics are reproduced from a fresh clone with no manual steps |
| P12-02 | Follow the README Quick Start **literally**, as a newcomer would | Every command works as written. Note any step that was missing |
| P12-03 | Follow RUNBOOK → "Rollback (index)" literally against Compose or kind | Works as documented |
| P12-04 | Read RUNBOOK → "Swap in a secure guideline repository" | Covers the `DocumentSource` protocol, ACL filtering, re-annotation, re-tuning and the sign-off checklist |
| P12-05 | Check the metrics in README, technical-summary and evaluation-report | All three show **the same numbers** |
| P12-06 | `git log --all -p \| grep -iE "secret\|password=" \| head` and gitleaks | Only dev placeholders appear |
| P12-07 | Check `LICENSE` (MIT) and `THIRD_PARTY_NOTICES.md` | Both present and current |

---

## Results log template

Paste this into `docs/project/manual-test-log.md`:

```markdown
| ID | Date | Result (✅/❌/⚠️) | Notes / evidence (screenshot, output path) |
|----|------|------------------|---------------------------------------------|
| P0-01 | | | |
```

**When something fails:** log it, finish the rest of that phase, then fix it before starting the next phase. The later phases rely on the earlier ones, so a failure in Phases 1–4 makes everything after it unreliable.

If a check doesn't behave as described, paste me the output and I'll give you the fix as a full file rewrite.
