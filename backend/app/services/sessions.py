"""단일 활성 로그인 생성과 토큰 발급."""

import secrets, uuid
from sqlalchemy import update
from app.models import Member, LoginSession, RefreshToken, now
from app.core.security import digest, cookies
from app.db.controls import locked

from app.api.serializers import member_json


def new_session(db, member, response):
    # Serialize competing logins for one member in PostgreSQL.
    locked(db, Member, member.id)
    db.execute(
        update(LoginSession)
        .where(LoginSession.member_id == member.id, LoginSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )
    csrf_value = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(48)
    session = LoginSession(
        id=str(uuid.uuid4()),
        member_id=member.id,
        expires_at=now() + 7 * 86400,
        csrf_digest=digest(csrf_value),
    )
    db.add(session)
    db.flush()
    db.add(
        RefreshToken(
            id=str(uuid.uuid4()),
            session_id=session.id,
            digest=digest(refresh),
            expires_at=session.expires_at,
        )
    )
    cookies(response, session, refresh, csrf_value)
    return member_json(member)
