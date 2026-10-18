"""Database-backed counters and locks shared by authentication flows."""

from fastapi import HTTPException
from sqlalchemy import select
from app.models import Limit, now


def fail(db, status, message, retry_after=None):
    db.commit()  # Failed attempts must survive an HTTP error.
    # 남은 대기 초가 있을 때만 클라이언트에 다음 시도 시점을 알려줍니다.
    headers = {"Retry-After": str(int(retry_after))} if retry_after else None
    raise HTTPException(status, message, headers=headers)


def locked(db, model, value):
    return db.scalar(
        select(model)
        .where(model.id == value)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def get_limit(db, key, seconds=900):
    row = db.scalar(select(Limit).where(Limit.key == key).with_for_update())
    if not row:
        row = Limit(key=key)
        db.add(row)
        db.flush()
    if now() >= row.started_at + seconds:
        row.started_at = now()
        row.count = 0
        row.blocked_until = 0
    return row
