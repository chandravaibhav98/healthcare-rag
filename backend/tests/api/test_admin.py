"""Admin API behaviour on SQLite and PostgreSQL (plan Phase 5).

Every admin endpoint is exercised here for its happy path, filters, sorting, pagination
and errors; who may call it is covered by test_rbac_matrix.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.api.routes.admin import PREFIX
from app.core.security import Role
from app.services import maintenance
from tests.support import AuthedClient

ANSWERABLE = "How long should hand hygiene with alcohol-based handrub take?"
OFF_TOPIC = "What is the recommended dose of the yellow fever vaccine?"
PHI = "Patient MRN 12345678 born 03/04/1950: when should gloves be worn?"


def _seed_queries(api: AuthedClient) -> None:
    for q in (ANSWERABLE, ANSWERABLE, OFF_TOPIC, PHI):
        assert api.ask(q, Role.USER).status_code == 200
    api.flush_query_log()


def _queries(api: AuthedClient, **params: Any) -> dict[str, Any]:
    resp = api.get(f"{PREFIX}/queries", Role.REVIEWER, params=params)
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _first(api: AuthedClient, **params: Any) -> dict[str, Any]:
    items = _queries(api, **params)["items"]
    assert items, params
    first: dict[str, Any] = items[0]
    return first


# --- query log ------------------------------------------------------------------------------
def test_qa_outcomes_are_persisted_redacted_and_attributed(api: AuthedClient) -> None:
    _seed_queries(api)
    page = _queries(api)
    assert page["total"] == 4
    stored = {item["question"] for item in page["items"]}
    assert PHI not in stored, "raw PHI must never reach the database (ADR-0009)"
    redacted = next(i for i in page["items"] if i["redactions"] > 0)
    assert "12345678" not in redacted["question"]
    assert "[ID]" in redacted["question"]
    me = api.get("/api/v1/auth/me", Role.USER).json()
    assert {i["user_id"] for i in page["items"]} == {me["id"]}
    assert all(i["index_version"] for i in page["items"])


def test_anonymous_queries_are_logged_without_user(api: AuthedClient) -> None:
    api.ask(ANSWERABLE, None)
    api.flush_query_log()
    assert _first(api)["user_id"] is None


def test_query_filters_sort_and_pagination(api: AuthedClient) -> None:
    _seed_queries(api)
    assert _queries(api, status="needs_review")["total"] >= 1
    validated = _queries(api, status="validated")
    assert all(i["status"] == "validated" for i in validated["items"])
    assert _queries(api, q="handrub")["total"] == 2
    assert api.get(f"{PREFIX}/queries", params={"min_confidence": 2}).status_code == 422

    asc = _queries(api, sort="confidence", order="asc")["items"]
    confidences = [i["confidence"] for i in asc]
    assert confidences == sorted(confidences)

    page1 = _queries(api, limit=3, offset=0)
    page2 = _queries(api, limit=3, offset=3)
    assert page1["total"] == page2["total"] == 4
    assert len(page1["items"]) == 3
    assert len(page2["items"]) == 1
    assert not {i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]}

    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert _queries(api, **{"from": future})["total"] == 0
    assert api.get(f"{PREFIX}/queries", params={"sort": "question"}).status_code == 422
    assert api.get(f"{PREFIX}/queries", params={"limit": 500}).status_code == 422


def test_query_detail_includes_evidence_and_withheld_candidate(api: AuthedClient) -> None:
    _seed_queries(api)
    abstained = _first(api, status="needs_review")
    detail = api.get(f"{PREFIX}/queries/{abstained['id']}", Role.REVIEWER).json()
    assert detail["citations"], "abstentions still carry candidate sources (ADR-0007)"
    assert set(detail["signals"]) >= {"coverage", "query_support", "retrieval_score"}
    assert detail["review"] is None
    assert api.get(f"{PREFIX}/queries/{uuid.uuid4()}").status_code == 404
    assert api.get(f"{PREFIX}/queries/not-a-uuid").status_code == 422


# --- reviews and the gold feedback loop -------------------------------------------------------
def test_review_queue_review_update_and_gold_export(api: AuthedClient) -> None:
    _seed_queries(api)
    pending = api.get(f"{PREFIX}/reviews", Role.REVIEWER).json()
    assert pending["total"] >= 1
    assert all(item["review"] is None for item in pending["items"])
    target = pending["items"][0]["query"]

    detail = api.get(f"{PREFIX}/queries/{target['id']}").json()
    chunk = detail["citations"][0]["chunk_id"]
    url = f"{PREFIX}/reviews/{target['id']}"

    bad = api.post(url, Role.REVIEWER, json={"verdict": "correct"})
    assert bad.status_code == 422, "a correction must say which chunks are right"

    created = api.post(url, Role.REVIEWER, json={"verdict": "reject", "note": "wrong doc"})
    assert created.status_code == 201
    updated = api.post(
        url,
        Role.REVIEWER,
        json={"verdict": "correct", "corrected_citations": [chunk], "promote_to_gold": True},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"], "one review per query (upsert)"

    after = api.get(f"{PREFIX}/reviews", Role.REVIEWER).json()
    assert target["id"] not in {i["query"]["id"] for i in after["items"]}
    reviewed = api.get(f"{PREFIX}/reviews", params={"status": "reviewed", "verdict": "correct"})
    assert reviewed.json()["total"] == 1
    promoted = api.get(f"{PREFIX}/reviews", params={"status": "all", "promoted": True})
    assert promoted.json()["total"] == 1
    assert _queries(api, reviewed=True)["total"] == 1

    export = api.get(f"{PREFIX}/reviews/export/gold.jsonl", Role.REVIEWER)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/x-ndjson")
    lines = export.text.splitlines()
    assert len(lines) == 1
    item = json.loads(lines[0])
    assert item["g2"] == [chunk]
    assert item["kind"] == "direct"
    assert item["source"]["verdict"] == "correct"
    assert item["source"]["query_id"] == target["id"]

    assert (
        api.post(f"{PREFIX}/reviews/{uuid.uuid4()}", json={"verdict": "approve"}).status_code == 404
    )
    actions = [a["action"] for a in api.get(f"{PREFIX}/audit-log").json()["items"]]
    assert {"review.create", "review.update"} <= set(actions)


# --- statistics -------------------------------------------------------------------------------------
def test_review_rejects_chunk_ids_not_in_the_active_index(api: AuthedClient) -> None:
    """Manual test F-10: promoted corrections become gold labels, so their chunk_ids must
    be well-formed (schema) and exist in the active index (route)."""
    _seed_queries(api)
    target = api.get(f"{PREFIX}/reviews", Role.REVIEWER).json()["items"][0]["query"]
    url = f"{PREFIX}/reviews/{target['id']}"
    malformed = api.post(
        url, Role.REVIEWER, json={"verdict": "correct", "corrected_citations": ["not-a-chunk"]}
    )
    assert malformed.status_code == 422
    ghost = "who-xyz-999::no-such-section::0001"
    unknown = api.post(
        url, Role.REVIEWER, json={"verdict": "correct", "corrected_citations": [ghost]}
    )
    assert unknown.status_code == 422
    assert ghost in unknown.text


def test_index_versions_do_not_disclose_server_paths(api: AuthedClient) -> None:
    """Manual test F-11: reviewers can read index versions; the server path is withheld."""
    items = api.get(f"{PREFIX}/index/versions", Role.REVIEWER).json()["items"]
    assert items
    for item in items:
        assert "/" not in item["path"]
        assert "\\" not in item["path"]


def test_stats_window(api: AuthedClient) -> None:
    _seed_queries(api)
    stats = api.get(f"{PREFIX}/stats", Role.REVIEWER).json()
    assert stats["total"] == 4
    assert stats["validated"] + stats["needs_review"] == 4
    assert stats["pass_rate"] == pytest.approx(stats["validated"] / 4)
    assert stats["latency_p50_ms"] <= stats["latency_p95_ms"]
    assert 0 <= stats["mean_confidence"] <= 1
    assert sum(p["total"] for p in stats["series"]) == 4
    bins = stats["confidence_histogram"]
    assert len(bins) == 10
    assert sum(b["count"] for b in bins) == 4
    assert bins[0]["lower"] == 0.0
    assert bins[-1]["upper"] == 1.0
    assert {t["topic"] for t in stats["top_topics"]} <= {"ppe", "hand-hygiene"}

    future = datetime.now(UTC) + timedelta(days=1)
    empty = api.get(
        f"{PREFIX}/stats",
        params={"from": future.isoformat(), "to": (future + timedelta(days=1)).isoformat()},
    ).json()
    assert empty["total"] == 0
    assert empty["pass_rate"] is None
    assert empty["series"] == []

    now = datetime.now(UTC)
    inverted = {"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()}
    assert api.get(f"{PREFIX}/stats", params=inverted).status_code == 422
    naive = {"from": "2026-01-01T00:00:00"}
    assert api.get(f"{PREFIX}/stats", params=naive).status_code == 422
    too_long = {"from": (now - timedelta(days=400)).isoformat(), "to": now.isoformat()}
    assert api.get(f"{PREFIX}/stats", params=too_long).status_code == 422
    # Regression (Schemathesis, Phase 7): the default window must not underflow year 1.
    assert api.get(f"{PREFIX}/stats", params={"to": "0001-01-01T00:00:00Z"}).status_code == 422


# --- runtime configuration ------------------------------------------------------------------------------
def _config_body(version: int, threshold: float, comment: str = "tighten") -> dict[str, Any]:
    return {
        "expected_version": version,
        "values": {
            "threshold": threshold,
            "retrieval_floor": 0.15,
            "weights": {"coverage": 0.2, "query_support": 0.6, "retrieval": 0.2},
        },
        "comment": comment,
    }


def test_config_update_is_applied_versioned_and_audited(api: AuthedClient) -> None:
    initial = api.get(f"{PREFIX}/config", Role.REVIEWER).json()
    assert initial["version"] == 0
    assert initial["values"]["threshold"] == 0.6

    before = api.ask(ANSWERABLE).json()
    assert before["status"] == "validated"

    updated = api.put(f"{PREFIX}/config", json=_config_body(0, 0.99))
    assert updated.status_code == 200
    assert updated.json()["version"] == 1
    assert updated.json()["updated_by"] == api.get("/api/v1/auth/me").json()["id"]

    after = api.ask(ANSWERABLE).json()
    assert after["status"] == "needs_review", "the new threshold applies to the next request"
    assert after["confidence"] == pytest.approx(before["confidence"])

    stale = api.put(f"{PREFIX}/config", json=_config_body(0, 0.5))
    assert stale.status_code == 409, "optimistic lock: version 0 is no longer current"

    entry = api.get(f"{PREFIX}/audit-log", params={"action": "config."}).json()["items"][0]
    assert entry["details"]["before"]["threshold"] == 0.6
    assert entry["details"]["after"]["threshold"] == 0.99
    assert entry["actor_email"] == "admin@example.org"


@pytest.mark.parametrize(
    "values",
    [
        {
            "threshold": 1.5,
            "retrieval_floor": 0.1,
            "weights": {"coverage": 0.2, "query_support": 0.6, "retrieval": 0.2},
        },
        {
            "threshold": 0.6,
            "retrieval_floor": 0.1,
            "weights": {"coverage": 0.5, "query_support": 0.6, "retrieval": 0.2},
        },
    ],
    ids=["threshold-out-of-range", "weights-do-not-sum-to-1"],
)
def test_config_validation(api: AuthedClient, values: dict[str, Any]) -> None:
    body = {"expected_version": 0, "values": values, "comment": "bad"}
    assert api.put(f"{PREFIX}/config", json=body).status_code == 422


def test_config_poller_applies_changes_made_elsewhere(api: AuthedClient) -> None:
    """Simulate another pod: write app_config directly, then run one poll tick."""
    from app.repositories import app_config as config_repo
    from app.services.tuning import Tuning

    async def write_and_sync() -> bool:
        async with api.db.session() as s:
            values = Tuning(threshold=0.42, retrieval_floor=0.1).to_values()
            config_repo.add(s, version=1, values=values, created_by=None, comment="pod B")
            await s.commit()
        async with api.db.session() as s:
            changed: bool = await api.app.state.config_service.sync(s)
            return changed

    assert api.run(write_and_sync) is True
    assert api.app.state.tuning.get().threshold == 0.42


# --- evaluation runs ---------------------------------------------------------------------------------
def test_eval_run_lifecycle_with_fake_runner(api: AuthedClient) -> None:
    calls: list[float] = []

    def runner(index: Any, settings: Any) -> dict[str, Any]:
        calls.append(settings.confidence_threshold)
        return {"scorecard": {"p@5": 0.5, "pass_rate": 0.9}, "index_version": index.index_version}

    api.app.state.eval_service._runner = runner
    started = api.post(f"{PREFIX}/eval-runs")
    assert started.status_code == 202
    run = started.json()
    assert run["status"] == "queued"
    assert run["split"] == "dev"
    api.run(api.app.state.eval_service.wait)

    done = api.get(f"{PREFIX}/eval-runs/{run['id']}", Role.REVIEWER).json()
    assert done["status"] == "succeeded"
    assert done["scorecard"] == {"p@5": 0.5, "pass_rate": 0.9}
    assert done["summary"]["index_version"] == run["index_version"]
    assert calls == [0.6], "a run uses the live tuning"

    listing = api.get(f"{PREFIX}/eval-runs", Role.REVIEWER, params={"status": "succeeded"})
    assert listing.json()["total"] == 1
    assert api.get(f"{PREFIX}/eval-runs/{uuid.uuid4()}").status_code == 404


def test_failed_eval_run_is_recorded(api: AuthedClient) -> None:
    def runner(*_: Any) -> dict[str, Any]:
        raise RuntimeError("gold labels do not match")

    api.app.state.eval_service._runner = runner
    run = api.post(f"{PREFIX}/eval-runs").json()
    api.run(api.app.state.eval_service.wait)
    failed = api.get(f"{PREFIX}/eval-runs/{run['id']}").json()
    assert failed["status"] == "failed"
    assert "gold labels do not match" in failed["error"]


def test_only_one_eval_run_at_a_time(api: AuthedClient) -> None:
    from app.repositories import eval_runs as run_repo

    async def queued_elsewhere() -> None:
        async with api.db.session() as s:
            run_repo.add(s, split="dev", triggered_by=None)
            await s.commit()

    api.run(queued_elsewhere)
    assert api.post(f"{PREFIX}/eval-runs").status_code == 409


# --- index versions and corpus --------------------------------------------------------------------------
def test_index_versions_activate_and_rebuild(api: AuthedClient) -> None:
    versions = api.get(f"{PREFIX}/index/versions", Role.REVIEWER).json()
    assert versions["total"] == 1
    boot = versions["items"][0]
    assert boot["is_active"]
    assert boot["source"] == "boot"
    assert boot["corpus_hash"]
    assert boot["chunk_count"] > 0

    status = api.get(f"{PREFIX}/index/rebuild").json()
    assert status["allowed"] is True
    assert status["running"] is False
    assert api.post(f"{PREFIX}/index/rebuild").status_code == 202
    api.run(api.app.state.index_service.wait_for_rebuild)
    status = api.get(f"{PREFIX}/index/rebuild").json()
    assert status["last_error"] is None, status
    rebuilt = status["last_version"]

    versions = api.get(f"{PREFIX}/index/versions").json()["items"]
    by_version = {v["version"]: v for v in versions}
    assert rebuilt in by_version
    # Same corpus, different chunking config in the fixture boot index → new version.
    assert by_version[rebuilt]["is_active"] is (rebuilt == boot["version"])

    activated = api.post(f"{PREFIX}/index/versions/{rebuilt}/activate")
    assert activated.status_code == 200
    assert activated.json()["is_active"]
    assert api.ask(ANSWERABLE).json()["meta"]["index_version"] == rebuilt
    assert api.client.get("/version").json()["index_version"] == rebuilt
    actives = [v for v in api.get(f"{PREFIX}/index/versions").json()["items"] if v["is_active"]]
    assert [v["version"] for v in actives] == [rebuilt]

    assert api.post(f"{PREFIX}/index/versions/ffffffffffff/activate").status_code == 404
    assert api.post(f"{PREFIX}/index/versions/NOT-HEX/activate").status_code == 422
    actions = {a["action"] for a in api.get(f"{PREFIX}/audit-log").json()["items"]}
    assert {"index.rebuild", "index.activate"} <= actions


def test_documents_inventory(api: AuthedClient) -> None:
    docs = api.get(f"{PREFIX}/documents", Role.REVIEWER).json()
    assert docs["total"] == 2
    assert [d["doc_id"] for d in docs["items"]] == ["cdc-tst-002", "who-tst-001"]
    assert all(d["chunk_count"] > 0 for d in docs["items"])
    assert all(d["token_count"] > 0 for d in docs["items"])
    assert api.get(f"{PREFIX}/documents", params={"source_org": "who"}).json()["total"] == 1
    assert api.get(f"{PREFIX}/documents", params={"status": "superseded"}).json()["total"] == 1
    assert api.get(f"{PREFIX}/documents", params={"topic": "hand-hygiene"}).json()["total"] == 1
    assert api.get(f"{PREFIX}/documents", params={"q": "revised"}).json()["total"] == 1
    desc = api.get(f"{PREFIX}/documents", params={"order": "desc", "limit": 1}).json()
    assert desc["items"][0]["doc_id"] == "who-tst-001"
    assert desc["total"] == 2
    assert api.get(f"{PREFIX}/documents", params={"sort": "title"}).status_code == 422


# --- audit log and retention ---------------------------------------------------------------------------------
def test_audit_log_filters(api: AuthedClient) -> None:
    api.login("admin@example.org", "wrong")
    everything = api.get(f"{PREFIX}/audit-log").json()
    assert everything["total"] == 4  # three persona logins + the failure
    failures = api.get(f"{PREFIX}/audit-log", params={"action": "auth.login_failed"}).json()
    assert failures["total"] == 1
    assert failures["items"][0]["actor_email"] == "admin@example.org"
    mine = api.get(f"{PREFIX}/audit-log", params={"actor_email": "Reviewer@Example.org"}).json()
    assert mine["total"] == 1
    assert mine["items"][0]["action"] == "auth.login"
    oldest = api.get(f"{PREFIX}/audit-log", params={"order": "asc", "limit": 1}).json()
    assert oldest["items"][0]["action"] == "auth.login"


def test_retention_purge(api: AuthedClient) -> None:
    _seed_queries(api)
    later = datetime.now(UTC) + timedelta(days=31)
    result = api.run(maintenance.purge, api.db, 30, later)
    assert result.query_logs == 4
    assert _queries(api)["total"] == 0
    entry = api.get(f"{PREFIX}/audit-log", params={"action": "retention."}).json()["items"][0]
    assert entry["details"]["query_logs"] == 4
    again = api.run(maintenance.purge, api.db, 30, later)
    assert again.query_logs == 0


def test_readiness_checks_the_database(api: AuthedClient) -> None:
    ready = api.client.get("/readyz").json()
    assert ready["checks"] == {"index": "ok", "database": "ok"}


def test_metrics_label_admin_routes_by_full_template(api: AuthedClient) -> None:
    api.get(f"{PREFIX}/queries/{uuid.uuid4()}")
    metrics = api.client.get("/metrics").text
    assert 'route="/api/v1/admin/queries/{query_id}"' in metrics


def test_more_query_filters(api: AuthedClient) -> None:
    _seed_queries(api)
    version = _first(api)["index_version"]
    assert _queries(api, index_version=version)["total"] == 4
    assert _queries(api, index_version="000000000000")["total"] == 0
    assert all(i["confidence"] <= 0.5 for i in _queries(api, max_confidence=0.5)["items"])
    reason = _first(api, status="needs_review")["reason"]
    assert reason
    assert _queries(api, reason=reason)["total"] >= 1
    assert _queries(api, reviewed=False)["total"] == 4


def test_rebuild_failure_is_reported_and_audited(api: AuthedClient, tmp_path: Any) -> None:
    api.app.state.index_service._corpus_dir = tmp_path / "missing-corpus"
    assert api.post(f"{PREFIX}/index/rebuild").status_code == 202
    assert api.post(f"{PREFIX}/index/rebuild").status_code in (202, 409)
    api.run(api.app.state.index_service.wait_for_rebuild)
    status = api.get(f"{PREFIX}/index/rebuild").json()
    assert status["running"] is False
    assert status["last_error"]
    actions = {a["action"] for a in api.get(f"{PREFIX}/audit-log").json()["items"]}
    assert "index.rebuild_failed" in actions


def test_rebuild_is_refused_in_production(db_app_factory: Any, sqlite_database_url: str) -> None:
    from fastapi.testclient import TestClient

    app = db_app_factory(
        sqlite_database_url,
        app_env="production",
        jwt_secret="p" * 40,
        log_question_text=False,
        allow_index_rebuild=True,  # even when asked for, production never rebuilds
    )
    with TestClient(app) as client:
        api = AuthedClient.create(client)
        assert api.get(f"{PREFIX}/index/rebuild").json()["allowed"] is False
        refused = api.post(f"{PREFIX}/index/rebuild")
        assert refused.status_code == 403
        cookie = api.login("admin@example.org").headers["set-cookie"]
        assert "Secure" in cookie, "production cookies are Secure by default"


def test_activating_a_corrupted_version_is_409_and_keeps_serving(api: AuthedClient) -> None:
    import shutil

    assert api.post(f"{PREFIX}/index/rebuild").status_code == 202
    api.run(api.app.state.index_service.wait_for_rebuild)
    status = api.get(f"{PREFIX}/index/rebuild").json()
    version = status["last_version"]
    row = next(
        v for v in api.get(f"{PREFIX}/index/versions").json()["items"] if v["version"] == version
    )
    if row["is_active"]:
        pytest.skip("rebuild produced the boot version; nothing to corrupt safely")
    # The API returns only the folder name (F-11); the location comes from the service.
    path = api.app.state.index_service.store_dir / version
    assert row["path"] == version
    faiss = path / "index.faiss"
    data = bytearray(faiss.read_bytes())
    data[-1] ^= 0xFF
    faiss.write_bytes(bytes(data))
    resp = api.post(f"{PREFIX}/index/versions/{version}/activate")
    assert resp.status_code == 409
    assert "failed verification" in resp.json()["detail"]
    assert api.ask(ANSWERABLE).status_code == 200, "the previous index keeps serving"
    shutil.rmtree(path)


def test_index_activation_on_another_pod_is_followed(api: AuthedClient) -> None:
    from app.repositories import index_versions as version_repo

    assert api.post(f"{PREFIX}/index/rebuild").status_code == 202
    api.run(api.app.state.index_service.wait_for_rebuild)
    target = api.get(f"{PREFIX}/index/rebuild").json()["last_version"]
    current = api.client.get("/version").json()["index_version"]
    if target == current:
        pytest.skip("rebuild produced the boot version")

    async def activate_elsewhere_and_poll() -> bool:
        async with api.db.session() as s:
            await version_repo.set_active(s, target)
            await s.commit()
        async with api.db.session() as s:
            switched: bool = await api.app.state.index_service.sync_active(s)
            return switched

    assert api.run(activate_elsewhere_and_poll) is True
    assert api.client.get("/version").json()["index_version"] == target
