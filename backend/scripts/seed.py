"""Seed accounts and demo data (wrapped by scripts/seed.sh / .ps1).

    uv run python scripts/seed.py                 # admin from SEED_ADMIN_EMAIL/PASSWORD
    uv run python scripts/seed.py --demo          # + reviewer/user accounts, ~7 days of
                                                  #   query history and a few reviews
    uv run python scripts/seed.py --reset --demo  # wipe app data first (never in production)

Idempotent: existing accounts are kept (use --reset-password to change the admin's), and
demo rows (request_id "demo-…") are replaced, not duplicated. Demo queries are answered by
the real pipeline on the active index, so the dashboard shows genuine confidence values.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any, Final

from sqlalchemy import delete, select

from app.api.schemas.qa import QARequest
from app.core.config import DEV_JWT_SECRET, AppEnv, Settings, get_settings
from app.core.security import Role, hash_password
from app.db.base import utcnow
from app.db.migrations import head_revision
from app.db.models import (
    AppConfig,
    AuditLog,
    EvalRun,
    IndexVersion,
    QueryLog,
    RefreshToken,
    Review,
    User,
)
from app.db.session import Database
from app.rag.index.registry import IndexRegistry
from app.rag.runtime import build_runtime
from app.repositories import audit
from app.repositories import query_log as query_repo
from app.repositories import users as user_repo
from app.repositories.audit import SYSTEM
from app.services.qa_service import QAOutcome, QAService
from app.services.query_log_writer import outcome_to_row
from app.services.tuning import Tuning, TuningHolder

DEV_ADMIN_PASSWORD: Final = "change-me-admin"  # noqa: S105  (documented dev default, refused in prod)
DEMO_PREFIX: Final = "demo-"
DEMO_DAYS: Final = 7
DEMO_QUESTIONS: Final = 60
#: Typed by "users" in the demo to show redaction in the explorer (synthetic identifiers).
DEMO_PHI_QUESTIONS: Final = (
    "Patient MRN 48213377 had a needlestick, what is the first step?",
    "Mr Daniel Hughes, DOB 14/02/1957: how long to observe after his flu vaccine?",
)


class _Capture:
    def __init__(self) -> None:
        self.outcomes: list[QAOutcome] = []

    def observe(self, outcome: QAOutcome) -> None:
        self.outcomes.append(outcome)


def _check(settings: Settings) -> str:
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL is empty; set it in .env (see .env.example).")
    if not settings.seed_admin_email or settings.seed_admin_password is None:
        raise SystemExit("Set SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD (see .env.example).")
    if settings.app_env is AppEnv.PRODUCTION:
        password = settings.seed_admin_password.get_secret_value()
        if password == DEV_ADMIN_PASSWORD or len(password) < 12:
            raise SystemExit("production needs a SEED_ADMIN_PASSWORD of 12+ characters")
        if settings.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
            raise SystemExit("production needs a real JWT_SECRET")
    return settings.database_url.get_secret_value()


async def _ensure_user(
    db: Database, email: str, password: str, role: Role, *, reset_password: bool
) -> tuple[User, str]:
    async with db.session() as session:
        user = await user_repo.get_by_email(session, email)
        if user is None:
            user = user_repo.add(
                session,
                email=email,
                display_name=email.split("@")[0].title(),
                password_hash=hash_password(password),
                role=role.value,
            )
            action = "created"
        elif reset_password:
            user.password_hash = hash_password(password)
            user.role = role.value
            user.is_active = True
            action = "password reset"
        else:
            action = "exists (unchanged)"
        await session.flush()
        if action != "exists (unchanged)":
            audit.record(
                session,
                SYSTEM,
                f"seed.user_{action.split()[0]}",
                target_type="user",
                target_id=str(user.id),
                details={"email": email, "role": role.value},
            )
        await session.commit()
        return user, action


async def _reset(db: Database) -> None:
    async with db.session() as session:
        for model in (
            Review,
            QueryLog,
            EvalRun,
            RefreshToken,
            AuditLog,
            AppConfig,
            IndexVersion,
            User,
        ):
            await session.execute(delete(model))
        await session.commit()


def _demo_questions(rng: random.Random) -> list[str]:
    from evaluation.common import load_split

    pool = [item.question for item in load_split("dev")]
    rng.shuffle(pool)
    return pool[:DEMO_QUESTIONS] + list(DEMO_PHI_QUESTIONS)


def _answer_all(settings: Settings, questions: Sequence[str]) -> list[QAOutcome]:
    registry = IndexRegistry(lambda index: build_runtime(index, settings))
    registry.load(settings.index_dir)
    capture = _Capture()
    service = QAService(
        registry, tuning=TuningHolder(Tuning.from_settings(settings)), observers=(capture,)
    )
    for i, question in enumerate(questions):
        service.answer(QARequest(question=question, top_k=5), f"{DEMO_PREFIX}{i:04d}")
    return capture.outcomes


async def _seed_demo(db: Database, settings: Settings, users: dict[Role, User]) -> dict[str, int]:
    rng = random.Random(20261107)  # noqa: S311  (deterministic demo data, not security)
    outcomes = await asyncio.to_thread(_answer_all, settings, _demo_questions(rng))
    manifest_topics = _topics(settings)
    now = utcnow()
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        row = outcome_to_row(outcome, lambda doc_id: manifest_topics.get(doc_id, []))
        row["user_id"] = rng.choice([users[Role.USER].id, users[Role.REVIEWER].id, None])
        row["created_at"] = now - timedelta(days=rng.uniform(0, DEMO_DAYS))
        row["id"] = uuid.uuid4()
        rows.append(row)
    async with db.session() as session:
        await session.execute(delete(QueryLog).where(QueryLog.request_id.startswith(DEMO_PREFIX)))
        query_repo.add_many(session, rows)
        await session.flush()
        # A few reviews so the review history and gold export are not empty.
        reviewer = users[Role.REVIEWER]
        validated = [r for r in rows if r["status"] == "validated"][:2]
        abstained = [r for r in rows if r["status"] == "needs_review"]
        for r in validated:
            session.add(
                Review(
                    query_id=r["id"],
                    reviewer_id=reviewer.id,
                    verdict="approve",
                    note="Matches the cited guidance.",
                    promote_to_gold=True,
                )
            )
        if abstained:
            r = abstained[0]
            cited = [c["chunk_id"] for c in r["citations"]][:1]
            session.add(
                Review(
                    query_id=r["id"],
                    reviewer_id=reviewer.id,
                    verdict="correct",
                    note="Correct source, answer withheld on low support.",
                    corrected_citations=cited,
                    promote_to_gold=bool(cited),
                )
            )
        audit.record(session, SYSTEM, "seed.demo", details={"queries": len(rows)})
        await session.commit()
    return {
        "queries": len(rows),
        "validated": sum(r["status"] == "validated" for r in rows),
        "needs_review": sum(r["status"] == "needs_review" for r in rows),
        "redacted": sum(r["redactions"] > 0 for r in rows),
    }


def _topics(settings: Settings) -> dict[str, list[str]]:
    from app.rag.index.manifest import read_manifest

    documents = read_manifest(settings.index_dir)["corpus"]["documents"]
    return {str(d["doc_id"]): list(d.get("topic", [])) for d in documents}


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    url = _check(settings)
    db = Database(url)
    try:
        revision = await db.schema_revision()
        if revision != head_revision():
            raise SystemExit(f"schema is at {revision or 'nothing'}; run scripts/db-migrate first")
        if args.reset:
            if settings.app_env is AppEnv.PRODUCTION:
                raise SystemExit("--reset is refused in production")
            await _reset(db)
            print("reset: application tables emptied")
        password = settings.seed_admin_password.get_secret_value()  # type: ignore[union-attr]
        admin, action = await _ensure_user(
            db,
            str(settings.seed_admin_email),
            password,
            Role.ADMIN,
            reset_password=args.reset_password,
        )
        print(f"admin {admin.email}: {action}")
        if args.demo:
            if settings.app_env is AppEnv.PRODUCTION:
                raise SystemExit("--demo is refused in production")
            domain = str(settings.seed_admin_email).partition("@")[2] or "example.org"
            users = {Role.ADMIN: admin}
            for role in (Role.REVIEWER, Role.USER):
                user, action = await _ensure_user(
                    db, f"{role.value}@{domain}", password, role, reset_password=args.reset_password
                )
                users[role] = user
                print(f"{role.value} {user.email}: {action} (password = SEED_ADMIN_PASSWORD)")
            counts = await _seed_demo(db, settings, users)
            print("demo data: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        async with db.session() as session:
            total = len((await session.execute(select(User.id))).all())
        print(f"accounts in database: {total}")
    finally:
        await db.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed accounts and demo data.")
    parser.add_argument("--demo", action="store_true", help="add demo accounts and history")
    parser.add_argument("--reset", action="store_true", help="empty app tables first (dev only)")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="set existing seeded accounts' passwords to SEED_ADMIN_PASSWORD",
    )
    asyncio.run(_run(parser.parse_args(argv)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
