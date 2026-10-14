"""Single-use numeric CAPTCHA proofs. No answer is exposed through the API."""

import base64
import hmac
import secrets
import uuid
from captcha.image import ImageCaptcha
from captcha.audio import AudioCaptcha
from fastapi import HTTPException
from app.models import CaptchaChallenge, now
from app.core.security import digest
from app.db.controls import fail, get_limit, locked

TTL = 120
MAX_ATTEMPTS = 5


def new_code():
    return f"{secrets.randbelow(100000):05d}"


def issue(db, address, previous_id=None):
    limit = get_limit(db, "captcha-issue:" + digest(address))
    if limit.count >= 30:
        fail(db, 429, "이미지 요청이 많습니다. 15분 후 다시 시도해주세요.")
    limit.count += 1
    if previous_id:
        old = locked(db, CaptchaChallenge, previous_id)
        if old:
            old.consumed_at = now()
            old.proof_digest = None
    code = new_code()
    identity = str(uuid.uuid4())
    challenge = CaptchaChallenge(
        id=identity,
        code_digest=digest("captcha:" + identity + ":" + code),
        expires_at=now() + TTL,
    )
    db.add(challenge)
    # Images and audio are generated for the response, never stored with the answer.
    picture = ImageCaptcha(width=220, height=80).generate(code).getvalue()
    audio = bytes(AudioCaptcha().generate(code))
    return {
        "id": challenge.id,
        "expires_at": challenge.expires_at,
        "image": "data:image/png;base64," + base64.b64encode(picture).decode(),
        "audio": "data:audio/wav;base64," + base64.b64encode(audio).decode(),
    }


def verify(db, challenge_id, answer, address):
    # IP limits also survive refreshes of individual challenges.
    limit = get_limit(db, "captcha-verify:" + digest(address))
    if limit.count >= 30:
        fail(db, 429, "확인 시도가 많습니다. 15분 후 다시 시도해주세요.")
    limit.count += 1
    row = locked(db, CaptchaChallenge, challenge_id)
    if not row or row.consumed_at or row.expires_at <= now():
        fail(db, 400, "이미지가 만료되었거나 사용되었습니다. 새 이미지를 받아주세요.")
    if row.attempts >= MAX_ATTEMPTS:
        fail(db, 429, "이 이미지의 입력 횟수를 초과했습니다. 새 이미지를 받아주세요.")
    if not hmac.compare_digest(
        row.code_digest, digest("captcha:" + row.id + ":" + answer)
    ):
        row.attempts += 1
        fail(db, 400, "이미지의 숫자와 일치하지 않습니다.")
    proof = secrets.token_urlsafe(32)
    row.proof_digest = digest(proof)
    row.verified_at = now()
    return {
        "captcha_token": row.id + ":" + proof,
        "expires_at": row.expires_at,
        "message": "자동 가입 방지 확인되었습니다.",
    }


def consume(db, token):
    parts = token.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(400, "자동 가입 방지 확인이 필요합니다.")
    row = locked(db, CaptchaChallenge, parts[0])
    if (
        not row
        or not row.verified_at
        or not row.proof_digest
        or row.consumed_at
        or row.expires_at <= now()
        or not hmac.compare_digest(row.proof_digest, digest(parts[1]))
    ):
        raise HTTPException(400, "자동 가입 방지를 다시 확인해주세요.")
    row.consumed_at = now()
