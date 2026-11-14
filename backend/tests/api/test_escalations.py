"""Users can escalate an answer to the review queue (Phase 6)."""

from __future__ import annotations

from app.api.routes.admin import PREFIX
from app.core.security import Role
from tests.support import AuthedClient

ANSWERABLE = "How long should hand hygiene with alcohol-based handrub take?"
URL = "/api/v1/escalations"


def _pending(api: AuthedClient) -> list[dict[str, object]]:
    items: list[dict[str, object]] = api.get(f"{PREFIX}/reviews").json()["items"]
    return items


def test_escalating_a_validated_answer_puts_it_in_the_queue(api: AuthedClient) -> None:
    answer = api.ask(ANSWERABLE).json()
    assert answer["status"] == "validated"
    assert _pending(api) == []

    note = "Seems short. Patient MRN 12345678 asked."
    resp = api.client.post(URL, json={"request_id": answer["meta"]["request_id"], "note": note})
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"

    pending = _pending(api)
    assert len(pending) == 1
    query = pending[0]["query"]
    assert isinstance(query, dict)
    assert query["escalated_at"] is not None
    detail = api.get(f"{PREFIX}/queries/{query['id']}").json()
    assert "12345678" not in detail["escalation_note"], "notes are redacted (ADR-0009)"
    assert api.get(f"{PREFIX}/queries", params={"escalated": True}).json()["total"] == 1

    again = api.client.post(URL, json={"request_id": answer["meta"]["request_id"]})
    assert again.status_code == 202
    assert again.json()["escalated_at"] == resp.json()["escalated_at"]
    actions = [a["action"] for a in api.get(f"{PREFIX}/audit-log").json()["items"]]
    assert {"query.escalated", "query.escalation_updated"} <= set(actions)


def test_reviewing_removes_it_from_the_pending_queue(api: AuthedClient) -> None:
    answer = api.ask(ANSWERABLE).json()
    api.client.post(URL, json={"request_id": answer["meta"]["request_id"]})
    query_id = _pending(api)[0]["query"]["id"]  # type: ignore[index]
    api.post(f"{PREFIX}/reviews/{query_id}", Role.REVIEWER, json={"verdict": "approve"})
    assert _pending(api) == []


def test_unknown_and_foreign_answers_are_404(api: AuthedClient) -> None:
    assert api.client.post(URL, json={"request_id": "0123456789abcdef"}).status_code == 404
    mine = api.ask(ANSWERABLE, Role.USER).json()["meta"]["request_id"]
    # Anonymous callers and other users cannot touch a signed-in user's answer.
    assert api.client.post(URL, json={"request_id": mine}).status_code == 404
    other = api.post(URL, Role.REVIEWER, json={"request_id": mine})
    assert other.status_code == 404
    assert api.post(URL, Role.USER, json={"request_id": mine}).status_code == 202


def test_validation(api: AuthedClient) -> None:
    assert api.client.post(URL, json={"request_id": "x"}).status_code == 422
    bad = {"request_id": "abc def ghi", "note": ""}
    assert api.client.post(URL, json=bad).status_code == 422
