"""Expired auth data cleanup; request-time expiry checks remain authoritative."""

import argparse
import json
from sqlalchemy import delete, select
from app.models import (
    Verification,
    CaptchaChallenge,
    Limit,
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
    # 사용 거절은 요청 시 만료 검사로 즉시 처리한다. 여기서는 쌓인 만료 행만 물리적으로 정리한다.
    ids = list(db.scalars(select(RefreshToken.id).where(RefreshToken.expires_at <= timestamp)
                          .with_for_update(skip_locked=True)))
    result["refresh_tokens"] = len(ids)
    if ids and not dry_run:
        db.execute(delete(RefreshToken).where(RefreshToken.id.in_(ids)))
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
