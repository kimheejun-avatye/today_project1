"""Expired auth data cleanup; request-time expiry checks remain authoritative."""

import argparse
import json
from sqlalchemy import delete, func, select, update, or_
from app.models import (
    Verification,
    CaptchaChallenge,
    Limit,
    LoginSession,
    RefreshToken,
    now,
)


def cleanup(db, retention_hours=24, dry_run=False):
    if retention_hours < 0:
        raise ValueError("retention_hours must be non-negative")
    timestamp = now()
    cutoff = timestamp - int(retention_hours * 3600)
    result = {}
    # Locks coordinate with API updates. SKIP LOCKED defers active requests to next run.
    for model, condition in (
        (Verification, Verification.expires_at < cutoff),
        (CaptchaChallenge, CaptchaChallenge.expires_at < cutoff),
        (
            Limit,
            (Limit.started_at + 900 < cutoff)
            & (Limit.blocked_until < cutoff)
            & (Limit.last_sent_at + 60 < cutoff),
        ),
    ):
        key = model.key if model is Limit else model.id
        ids = list(
            db.scalars(select(key).where(condition).with_for_update(skip_locked=True))
        )
        result[model.__tablename__] = len(ids)
        if ids and not dry_run:
            db.execute(delete(model).where(key.in_(ids)))
    sessions = list(
        db.scalars(
            select(LoginSession.id)
            .where(
                or_(LoginSession.expires_at < cutoff, LoginSession.revoked_at < cutoff)
            )
            .with_for_update(skip_locked=True)
        )
    )
    result["login_sessions"] = len(sessions)
    result["refresh_tokens"] = db.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.session_id.in_(sessions))
    )
    if sessions and not dry_run:
        # Remove entire token chains in one statement before their parent sessions.
        db.execute(delete(RefreshToken).where(RefreshToken.session_id.in_(sessions)))
        db.execute(delete(LoginSession).where(LoginSession.id.in_(sessions)))
    expired_payloads = list(
        db.scalars(
            select(RefreshToken.id)
            .where(
                RefreshToken.retry_payload.is_not(None),
                RefreshToken.retry_until < timestamp,
                RefreshToken.session_id.not_in(sessions),
            )
            .with_for_update(skip_locked=True)
        )
    )
    result["retry_payloads"] = len(expired_payloads)
    if expired_payloads and not dry_run:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.id.in_(expired_payloads))
            .values(retry_payload=None)
        )
    return result


if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as DatabaseSession
    import os

    parser = argparse.ArgumentParser(
        description="Clean auth records after 24 hours; never delete member content."
    )
    parser.add_argument("--retention-hours", type=int, default=24)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./diary.db"))
    with DatabaseSession(engine) as db, db.begin():
        print(
            json.dumps(
                {
                    "dry_run": args.dry_run,
                    "counts": cleanup(db, args.retention_hours, args.dry_run),
                }
            )
        )
