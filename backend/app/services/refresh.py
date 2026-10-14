"""재발급 토큰 회전과 재시도 유예. DB 커밋은 요청의 트랜잭션에 맡깁니다."""

import json
import secrets
import uuid
from collections.abc import Callable
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.models import LoginSession, RefreshToken, now
from app.core.security import digest, access, fernet
from app.db.controls import fail, locked


def rotate_refresh_token(
    db: Session, raw_token: str, validate_csrf: Callable[[LoginSession], None]
) -> tuple[LoginSession, str, str]:
    """로그인 기록, Refresh 원문, Access 토큰을 반환합니다.

    CSRF 검증은 잠근 로그인 기록으로 수행합니다. 회전한 직전 토큰의 정상
    재시도에는 같은 결과를 반환하지만, 유예 밖 재사용은 재발급을 차단합니다.
    """
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.digest == digest(raw_token))
    )
    if not token:
        raise HTTPException(401, "다시 로그인해주세요.")
    # 다른 재발급 요청과 같은 순서로 잠가 회전 결과가 갈라지지 않게 합니다.
    session = locked(db, LoginSession, token.session_id)
    token = locked(db, RefreshToken, token.id)
    if (
        not session
        or session.revoked_at
        or session.refresh_revoked_at
        or session.expires_at <= now()
        or token.expires_at <= now()
    ):
        raise HTTPException(401, "로그인이 종료되었습니다.")
    validate_csrf(session)
    # 5초는 만료 연장이 아니라 이미 회전한 토큰의 동일 응답 재전달 기간입니다.
    if token.rotated_at:
        successor = db.scalar(
            select(RefreshToken).where(RefreshToken.previous_id == token.id)
        )
        if (
            token.retry_until >= now()
            and token.retry_payload
            and successor
            and not successor.rotated_at
        ):
            payload = json.loads(fernet.decrypt(token.retry_payload.encode()))
            return session, payload["refresh"], payload["access"]
        session.refresh_revoked_at = now()
        token.retry_payload = None
        fail(db, 401, "이전 토큰 재사용을 발견했습니다. 다시 로그인해주세요.")
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session.id, RefreshToken.retry_until < now())
        .values(retry_payload=None)
    )
    raw = secrets.token_urlsafe(48)
    at = access(session)
    db.add(
        RefreshToken(
            id=str(uuid.uuid4()),
            session_id=session.id,
            digest=digest(raw),
            previous_id=token.id,
            expires_at=session.expires_at,
        )
    )
    token.rotated_at = now()
    token.retry_until = now() + 5
    token.retry_payload = fernet.encrypt(
        json.dumps({"refresh": raw, "access": at}).encode()
    ).decode()
    return session, raw, at
