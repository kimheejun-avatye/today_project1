"""members API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

from fastapi import Depends, Request, HTTPException
from app.db.session import db_session
from app.models import now
from app.core.security import current

from fastapi import APIRouter
from app.schemas import Proof, Profile
from app.api.serializers import member_json
from app.services.verification import proof_record

router = APIRouter(tags=["members"])


@router.get("/api/me")
def me(request: Request, db=Depends(db_session)):
    return member_json(current(request, db)[0])


@router.patch("/api/me")
def profile(data: Profile, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    if not data.name.strip() or not data.nickname.strip():
        raise HTTPException(400, "이름과 닉네임을 입력해주세요.")
    m.name = data.name.strip()
    m.nickname = data.nickname.strip()
    return member_json(m)


@router.post("/api/me/email")
def change_email(data: Proof, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    if not m.password_hash:
        raise HTTPException(403, "Google 전용 계정은 변경할 수 없습니다.")
    v = proof_record(db, data, "EMAIL_CHANGE")
    if v.member_id != m.id:
        raise HTTPException(403, "본인의 인증만 사용할 수 있습니다.")
    m.email = v.email
    v.consumed_at = now()
    return member_json(m)
