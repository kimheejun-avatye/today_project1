import os, secrets, hmac, hashlib
from pathlib import Path
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
import jwt
from fastapi import HTTPException, Request
from app.models import now, Member

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
# Access는 짧게 사용하고, Refresh 교체로 전체 로그인 시간이 연장되지 않게 한다.
ACCESS_SECONDS = 300
REFRESH_SECONDS = 4 * 3600


def digest(value):
    # DB가 노출돼도 저장값 자체를 토큰으로 제출하지 못하도록 원문 대신 HMAC을 저장한다.
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def password_matches(hashed, password):
    try:
        return ph.verify(hashed or DUMMY, password) and bool(hashed)
    except VerificationError:
        return False


def signed_claims(kind, member_id, record_id, expires_at):
    # rid는 CSRF를 같은 로그인에 연결하기 위한 값이다. 일반 요청에서 DB 조회 키로 쓰지 않는다.
    # kind를 검사해 CSRF용 서명 토큰을 Access로 사용하는 것을 막는다.
    return {"sub": str(member_id), "rid": record_id, "iat": now(),
            "exp": expires_at, "iss": "diary-api", "aud": "diary-web", "kind": kind}


def access(token):
    # 예: 종료 2분 전에 재발급하면 Access도 2분만 유효해 전체 4시간을 넘지 않는다.
    return jwt.encode(signed_claims("access", token.member_id, token.id,
                      min(now() + ACCESS_SECONDS, token.expires_at)), SECRET, algorithm="HS256")


def decode(value, kind, allow_expired=False):
    try:
        claim = jwt.decode(value, SECRET, algorithms=["HS256"], audience="diary-web",
                           issuer="diary-api", options={"require": ["sub", "rid", "iat", "exp", "iss", "aud", "kind"], "verify_exp": not allow_expired})
        if claim["kind"] != kind or any(not isinstance(claim[k], str) or not claim[k] for k in ("sub", "rid")):
            raise ValueError()
        if not claim["sub"].isdigit():
            raise ValueError()
        return claim
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "로그인이 필요합니다. 작성한 내용은 유지됩니다.")


def csrf(request, record_id, member_id=None, allow_expired=False):
    # 쿠키·헤더 일치뿐 아니라 서명과 로그인별 ID를 확인한다. Origin 검사는 main.py에서 수행한다.
    value = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("csrf", "")
    if not value or not hmac.compare_digest(value, cookie):
        raise HTTPException(403, "보안 확인에 실패했습니다.")
    try:
        claim = decode(value, "csrf", allow_expired)
    except HTTPException:
        raise HTTPException(403, "보안 확인에 실패했습니다.")
    if claim["rid"] != record_id or (member_id is not None and claim["sub"] != str(member_id)):
        raise HTTPException(403, "보안 확인에 실패했습니다.")


def current(request: Request, db):
    # 세션/Refresh 테이블을 조회하지 않는다. 회원 존재 확인은 서비스 데이터 조회로 유지한다.
    # 따라서 로그아웃 전에 복사한 Access를 즉시 차단하지 않으며 최대 5분을 허용한다.
    claim = decode(request.cookies.get("access", ""), "access")
    member = db.get(Member, int(claim["sub"]))
    if not member:
        raise HTTPException(401, "로그인이 필요합니다.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf(request, claim["rid"], member.id)
    return member, claim


def clear_cookies(response):
    for key, path in [("access", "/"), ("refresh", "/api/auth"), ("csrf", "/")]:
        response.delete_cookie(key, path=path, secure=PRODUCTION, samesite="lax")


def cookies(response, token, refresh):
    remaining = max(0, token.expires_at - now())
    options = dict(secure=PRODUCTION, samesite="lax")
    response.set_cookie("access", access(token), max_age=min(ACCESS_SECONDS, remaining),
                        httponly=True, path="/", **options)
    response.set_cookie("refresh", refresh, max_age=remaining, httponly=True, path="/api/auth", **options)
    # CSRF는 JS가 헤더에 실어야 하므로 읽기 가능하다. Access·Refresh 원문은 HttpOnly로 보호한다.
    # nonce는 같은 초에 재발급해도 값이 달라지게 해 다른 탭의 쿠키 갱신을 식별한다.
    proof = jwt.encode({**signed_claims("csrf", token.member_id, token.id, token.expires_at),
                        "nonce": secrets.token_urlsafe(16)}, SECRET, algorithm="HS256")
    response.set_cookie("csrf", proof, max_age=remaining, httponly=False, path="/", **options)
    response.headers["X-Login-Expires-At"] = str(token.expires_at)
