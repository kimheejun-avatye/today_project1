"""Database-backed counters and locks shared by authentication flows."""

from fastapi import HTTPException
from sqlalchemy import select
from app.models import Limit, now


def fail(db, status, message):
    db.commit()  # Failed attempts must survive an HTTP error.
    raise HTTPException(status, message)


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
