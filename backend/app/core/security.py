import os, secrets, hmac, hashlib, base64
from pathlib import Path
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet
import jwt
from fastapi import HTTPException, Request
from app.models import now, Member, LoginSession

PRODUCTION = os.getenv("APP_ENV") == "production"
SECRET = os.getenv("APP_SECRET")
if not SECRET:
    if PRODUCTION:
        raise RuntimeError("APP_SECRET is required in production")
    path = Path(".dev-key")
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    SECRET = path.read_text().strip()
if len(SECRET) < 32:
    raise RuntimeError("APP_SECRET must contain at least 32 characters")
ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:5173").rstrip("/")
ph = PasswordHasher()
DUMMY = ph.hash(secrets.token_urlsafe(32))
fernet = Fernet(
    base64.urlsafe_b64encode(hashlib.sha256((SECRET + ":grace").encode()).digest())
)


def digest(value):
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def password_matches(hashed, password):
    try:
        return ph.verify(hashed or DUMMY, password) and bool(hashed)
    except VerificationError:
        return False


def access(session):
    return jwt.encode(
        {
            "sub": str(session.member_id),
            "sid": session.id,
            "iat": now(),
            "exp": min(now() + 900, session.expires_at),
            "iss": "diary-api",
            "aud": "diary-web",
            "kind": "access",
        },
        SECRET,
        algorithm="HS256",
    )


def csrf(request, session):
    value = request.headers.get("x-csrf-token", "")
    if not value or not hmac.compare_digest(digest(value), session.csrf_digest):
        raise HTTPException(403, "보안 확인에 실패했습니다. 화면을 새로고침해주세요.")


def current(request: Request, db):
    # First validate the issued JWT. A valid signature alone does not prove that
    # the login is still active; its server-side record remains authoritative.
    try:
        claim = jwt.decode(
            request.cookies.get("access", ""),
            SECRET,
            algorithms=["HS256"],
            audience="diary-web",
            issuer="diary-api",
            options={"require": ["sub", "sid", "iat", "exp", "iss", "aud", "kind"]},
        )
        if (
            claim["kind"] != "access"
            or not isinstance(claim["sub"], str)
            or not claim["sub"]
            or not isinstance(claim["sid"], str)
            or not claim["sid"]
        ):
            raise ValueError()
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "로그인이 필요합니다. 작성한 내용은 유지됩니다.")

    # Check this on every authenticated request, including JWTs copied before
    # logout, replacement login, or password reset. Do not fall back to JWT-only
    # access when the login record is unavailable.
    session = db.get(LoginSession, claim["sid"])
    if (
        not session
        or str(session.member_id) != claim["sub"]
        or session.revoked_at is not None
        or session.expires_at <= now()
    ):
        raise HTTPException(401, "로그인이 필요합니다. 작성한 내용은 유지됩니다.")
    member = db.get(Member, session.member_id)
    if not member:
        raise HTTPException(401, "로그인이 필요합니다. 작성한 내용은 유지됩니다.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf(request, session)
    return member, session


def cookies(response, session, refresh=None, csrf_value=None, access_value=None):
    options = dict(secure=PRODUCTION, samesite="lax")
    response.set_cookie(
        "access",
        access_value or access(session),
        max_age=max(0, min(900, session.expires_at - now())),
        httponly=True,
        path="/",
        **options,
    )
    if refresh:
        response.set_cookie(
            "refresh",
            refresh,
            max_age=max(0, session.expires_at - now()),
            httponly=True,
            path="/api/auth",
            **options,
        )
    if csrf_value:
        response.set_cookie(
            "csrf",
            csrf_value,
            max_age=max(0, session.expires_at - now()),
            httponly=False,
            path="/",
            **options,
        )
