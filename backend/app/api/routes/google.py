"""google API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

from fastapi import Depends, Request, Response, HTTPException
from sqlalchemy import select
from app.db.session import db_session
from app.models import Member, now
from app.core.security import password_matches, current
from app.services import captcha as captcha_service
from app.core.privacy import NOTICE, validate_consent

from fastapi import APIRouter
from app.schemas import GoogleInput
from app.services.verification import email_key
from app.services.tokens import issue_tokens
from app.services.google import google_claim

router = APIRouter(tags=["google"])


@router.post("/api/auth/google/prepare")
def prepare_google(data: GoogleInput, db=Depends(db_session)):
    claim = google_claim(data.credential)
    member = db.scalar(select(Member).where(Member.google_subject == claim["sub"]))
    if member:
        return {"needs_profile": False}
    existing = db.scalar(
        select(Member).where(Member.email == email_key(claim["email"]))
    )
    if existing:
        raise HTTPException(
            409,
            "기존 이메일 계정으로 로그인한 뒤 내 정보에서 Google 계정을 연결해주세요.",
        )
    return {
        "needs_profile": True,
        "email": email_key(claim["email"]),
        "name": claim.get("name", ""),
    }


@router.post("/api/auth/google")
def google_login(
    data: GoogleInput, request: Request, response: Response, db=Depends(db_session)
):
    claim = google_claim(data.credential)
    member = db.scalar(select(Member).where(Member.google_subject == claim["sub"]))
    if data.intent == "login":
        if not member:
            raise HTTPException(
                403,
                "아직 가입되지 않은 Google 계정입니다. 회원가입을 먼저 진행해주세요.",
            )
        return issue_tokens(db, member, response)
    email = email_key(claim["email"])
    if data.intent == "link":
        active, _ = current(request, db)
        if (
            active.email != email
            or not data.consent
            or not password_matches(active.password_hash, data.link_password)
        ):
            raise HTTPException(
                403, "기존 계정으로 로그인한 뒤 비밀번호와 연결 동의를 확인해주세요."
            )
        if (member and member.id != active.id) or (
            active.google_subject and active.google_subject != claim["sub"]
        ):
            raise HTTPException(409, "다른 Google 계정이 연결되어 있습니다.")
        active.google_subject = claim["sub"]
        return issue_tokens(db, active, response)
    if member:
        raise HTTPException(
            409, "이미 가입된 Google 계정입니다. 로그인 화면에서 로그인해주세요."
        )
    if db.scalar(select(Member).where(Member.email == email)):
        raise HTTPException(
            409,
            "기존 이메일 계정으로 로그인한 뒤 내 정보에서 Google 계정을 연결해주세요.",
        )
    validate_consent(data.privacy_consent, data.privacy_consent_version)
    if not data.name.strip() or not data.nickname.strip():
        raise HTTPException(400, "Google 신규 가입에는 이름·닉네임이 필요합니다.")
    captcha_service.consume(db, data.captcha_token)
    member = Member(
        email=email,
        google_subject=claim["sub"],
        name=data.name.strip(),
        nickname=data.nickname.strip(),
        privacy_consent_version=NOTICE["version"],
        privacy_consented_at=now(),
    )
    db.add(member)
    db.flush()
    return issue_tokens(db, member, response)
