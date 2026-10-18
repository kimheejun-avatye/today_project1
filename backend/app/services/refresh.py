"""Refresh 한 행의 해시만 교체한다. 이전 토큰 이력과 재시도 유예는 보관하지 않는다."""
import secrets, hmac
from fastapi import HTTPException
from sqlalchemy import delete, update
from app.models import RefreshToken, now
from app.core.security import digest, csrf
from app.db.controls import locked


def rotate_refresh_token(db, raw_token, request):
    identity = raw_token.partition(".")[0]
    # 재발급·로그아웃이 같은 기록을 동시에 변경하지 않도록 잠근 뒤 검증한다.
    token = locked(db, RefreshToken, identity)
    if not token or token.expires_at <= now() or not hmac.compare_digest(token.digest, digest(raw_token)):
        raise HTTPException(401, "로그인이 종료되었습니다.")
    csrf(request, token.id, token.member_id)
    raw = token.id + "." + secrets.token_urlsafe(48)
    # 기존 해시가 여전히 일치할 때만 갱신한다. 행 잠금이 없는 SQLite에서도 중복 회전을 막는다.
    # expires_at은 갱신하지 않아 계속 사용해도 최초 로그인부터 4시간 뒤 종료된다.
    result = db.execute(update(RefreshToken).where(RefreshToken.id == token.id,
        RefreshToken.digest == digest(raw_token), RefreshToken.expires_at > now())
        .values(digest=digest(raw)).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(401, "다시 로그인해주세요.")
    db.commit()
    return token, raw


def revoke_refresh_token(db, raw_token, request):
    identity = raw_token.partition(".")[0]
    if not raw_token:
        return
    # 회전 직후에도 같은 ID를 유지하므로, 이전 비밀값을 보낸 로그아웃도 해당 기록을 지울 수 있다.
    # 이때 권한은 ID만 믿지 않고 서명된 CSRF와 회원 연결로 확인한다.
    # 만료된 CSRF 허용은 기록 삭제에만 한정한다. Access 인증·재발급에는 적용하지 않는다.
    csrf(request, identity, allow_expired=True)
    token = locked(db, RefreshToken, identity)
    if token:
        csrf(request, identity, token.member_id, allow_expired=True)
        db.execute(delete(RefreshToken).where(RefreshToken.id == identity))
    db.commit()
