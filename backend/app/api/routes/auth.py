"""auth API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

import secrets, uuid, hmac
from fastapi import Depends, Request, Response, HTTPException
from sqlalchemy import select, update
from app.db.session import db_session
from app.models import Member, Verification, LoginSession, now
from app.core.security import (
    PRODUCTION,
    ph,
    digest,
    password_matches,
    current,
    csrf,
    cookies,
)
from app.db.controls import fail, locked, get_limit
from app.services import captcha as captcha_service
from app.core.privacy import NOTICE, validate_consent
from app.services.mail import send_code

from fastapi import APIRouter
from app.schemas import (
    EmailRequest,
    CaptchaRequest,
    CaptchaAnswer,
    CodeInput,
    Signup,
    Credentials,
    Reset,
)
from app.services.verification import email_key, proof_record
from app.services.sessions import new_session

from app.services.refresh import rotate_refresh_token

router = APIRouter(tags=["auth"])


@router.post("/api/auth/captcha")
def issue_captcha(data: CaptchaRequest, request: Request, db=Depends(db_session)):
    return captcha_service.issue(
        db, request.client.host if request.client else "unknown", data.previous_id
    )


@router.post("/api/auth/captcha/verify")
def verify_captcha(data: CaptchaAnswer, request: Request, db=Depends(db_session)):
    return captcha_service.verify(
        db, data.id, data.answer, request.client.host if request.client else "unknown"
    )


@router.post("/api/auth/email/request")
def request_email(data: EmailRequest, request: Request, db=Depends(db_session)):
    if data.purpose not in ("SIGNUP", "PASSWORD_RESET", "EMAIL_CHANGE"):
        raise HTTPException(400, "잘못된 인증 목적입니다.")
    captcha_service.consume(db, data.captcha_token)
    email = email_key(data.email)
    owner = None
    if data.purpose == "EMAIL_CHANGE":
        owner, _ = current(request, db)
        if not owner.password_hash:
            raise HTTPException(403, "Google 전용 계정은 이메일을 변경할 수 없습니다.")
    address = request.client.host if request.client else "unknown"
    ip = get_limit(db, "mail-ip:" + digest(address))
    if ip.count >= 20:
        fail(db, 429, "메일 요청이 많습니다. 15분 후 다시 시도해주세요.", retry_after=max(1, ip.started_at + 900 - now()))
    ip.count += 1
    existing = db.scalar(select(Member).where(Member.email == email))
    if data.purpose == "SIGNUP" and existing:
        fail(db, 409, "이미 가입된 이메일입니다")
    limit = get_limit(db, "mail:" + email + ":" + data.purpose)
    if limit.last_sent_at and now() - limit.last_sent_at < 60:
        fail(db, 429, "인증번호는 1분 간격으로 요청할 수 있습니다.", retry_after=max(1, 60 - (now() - limit.last_sent_at)))
    limit.last_sent_at = now()
    # 제한 기록의 잠금을 기다리는 동안 회원 상태가 바뀌었을 수 있어 다시 조회합니다.
    existing = db.scalar(select(Member).where(Member.email == email))
    # Recovery and email-change responses do not disclose account eligibility.
    allowed = (
        (data.purpose == "SIGNUP" and not existing)
        or (data.purpose == "PASSWORD_RESET" and existing and existing.password_hash)
        or (data.purpose == "EMAIL_CHANGE" and not existing)
    )
    flow = secrets.token_urlsafe(32)
    vid = str(uuid.uuid4())
    result = {
        "id": vid,
        "flow": flow,
        "message": "진행 가능한 주소라면 인증 메일을 보냈습니다. Google 가입자는 Google 로그인을 이용하세요.",
    }
    if not allowed:
        return result
    code = f"{secrets.randbelow(1000000):06d}"
    # SMTP 실패 시 이전 인증을 유지합니다. SMTP 접수 자체는 DB 롤백으로 취소할 수 없습니다.
    preview = send_code(email, code)
    db.execute(
        update(Verification)
        .where(
            Verification.email == email,
            Verification.purpose == data.purpose,
            Verification.consumed_at.is_(None),
        )
        .values(consumed_at=now())
    )
    db.add(
        Verification(
            id=vid,
            member_id=owner.id if owner else (existing.id if existing else None),
            email=email,
            purpose=data.purpose,
            code_digest=digest(vid + ":" + code),
            flow_digest=digest(flow),
            expires_at=now() + 600,
        )
    )
    if preview:
        result["dev_code"] = preview
    return result


@router.post("/api/auth/email/verify")
def verify_email(data: CodeInput, db=Depends(db_session)):
    v = proof_record(db, data, verified=False)
    limit = get_limit(db, "verify:" + v.email + ":" + v.purpose)
    if limit.count >= 5:
        fail(db, 429, "인증 시도 횟수를 초과했습니다. 15분 후 다시 시도해주세요.")
    if not hmac.compare_digest(v.code_digest, digest(v.id + ":" + data.code)):
        limit.count += 1
        fail(db, 400, "인증번호가 올바르지 않습니다.")
    v.verified_at = now()
    return {"verified": True}


@router.post("/api/auth/signup", status_code=201)
def signup(data: Signup, db=Depends(db_session)):
    validate_consent(data.privacy_consent, data.privacy_consent_version)
    if not data.name.strip() or not data.nickname.strip():
        raise HTTPException(400, "이름과 닉네임을 입력해주세요.")
    # Reject forged proofs before expensive hashing; recheck under the row lock after hashing.
    proof_record(db, data, "SIGNUP", lock=False)
    password_hash = ph.hash(data.password)
    v = proof_record(db, data, "SIGNUP")
    db.add(
        Member(
            email=v.email,
            password_hash=password_hash,
            name=data.name.strip(),
            nickname=data.nickname.strip(),
            privacy_consent_version=NOTICE["version"],
            privacy_consented_at=now(),
        )
    )
    # 회원 생성과 인증 소비가 같은 트랜잭션에서 함께 성공하거나 함께 취소됩니다.
    v.consumed_at = now()
    db.flush()
    return {"message": "가입했습니다. 로그인해주세요."}


@router.post("/api/auth/login")
def login(
    data: Credentials, request: Request, response: Response, db=Depends(db_session)
):
    email = email_key(data.email)
    address = request.client.host if request.client else "unknown"
    limits = [
        get_limit(db, "login:" + email),
        get_limit(db, "login-ip:" + digest(address)),
    ]
    if any(x.blocked_until > now() for x in limits):
        fail(db, 429, "잠시 기다린 뒤 다시 로그인해주세요.", retry_after=max(1, max(x.blocked_until for x in limits) - now()))
    member = db.scalar(select(Member).where(Member.email == email))
    if not password_matches(member.password_hash if member else None, data.password):
        for item in limits:
            item.count += 1
            if item.count >= 5:
                item.blocked_until = now() + min(300, 30 * 2 ** min(item.count - 5, 4))
        fail(db, 401, "이메일 또는 비밀번호를 확인해주세요.")
    limits[0].count = 0
    limits[0].blocked_until = 0
    return new_session(db, member, response)


@router.post("/api/auth/refresh")
def refresh(request: Request, response: Response, db=Depends(db_session)):
    session, refresh_token, access_token = rotate_refresh_token(
        db, request.cookies.get("refresh", ""), lambda session: csrf(request, session)
    )
    cookies(response, session, refresh_token, access_value=access_token)
    return {"renewed": True}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response, db=Depends(db_session)):
    member, session = current(request, db)
    session.revoked_at = now()
    for key, path in [("access", "/"), ("refresh", "/api/auth"), ("csrf", "/")]:
        response.delete_cookie(key, path=path, secure=PRODUCTION, samesite="lax")
    return {"ok": True}


@router.post("/api/auth/password/reset")
def reset(data: Reset, db=Depends(db_session)):
    v = proof_record(db, data, "PASSWORD_RESET")
    member = locked(db, Member, v.member_id)
    if not member or not member.password_hash or member.email != v.email:
        raise HTTPException(400, "비밀번호를 재설정할 수 없습니다.")
    member.password_hash = ph.hash(data.password)
    v.consumed_at = now()
    db.execute(
        update(LoginSession)
        .where(LoginSession.member_id == member.id)
        .values(revoked_at=now())
    )
    return {"message": "비밀번호를 변경했습니다. 다시 로그인해주세요."}
