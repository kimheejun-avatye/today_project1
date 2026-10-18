"""현재 Refresh 한 건만 저장하며, 로그인 유지 기간은 최초 발급부터 4시간이다."""
import secrets, uuid
from sqlalchemy import delete
from app.models import Member, RefreshToken, now
from app.core.security import digest, cookies, REFRESH_SECONDS
from app.db.controls import locked
from app.api.serializers import member_json


def issue_tokens(db, member, response):
    # 같은 회원의 동시 로그인을 직렬화해 현재 Refresh가 하나만 남도록 한다.
    # 기존 Refresh를 삭제해도 이미 발급한 Access는 자체 만료까지 유효하다.
    locked(db, Member, member.id)
    db.execute(delete(RefreshToken).where(RefreshToken.member_id == member.id))
    identity = str(uuid.uuid4())
    # 앞부분 ID는 기록을 찾는 용도다. 재발급 권한은 뒤의 난수까지 포함한 해시로 검증한다.
    raw = identity + "." + secrets.token_urlsafe(48)
    token = RefreshToken(id=identity, member_id=member.id, digest=digest(raw),
                         expires_at=now() + REFRESH_SECONDS)
    db.add(token)
    db.flush()
    db.commit()  # DB 저장이 확정된 뒤 쿠키를 발급해 저장 실패 시 로그인 성공을 응답하지 않는다.
    cookies(response, token, raw)
    return member_json(member)
