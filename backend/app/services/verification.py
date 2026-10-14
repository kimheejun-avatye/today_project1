"""이메일 정규화와 일회성 인증 증거 검증."""

import hmac
from fastapi import HTTPException
from app.models import Verification, now
from app.core.security import digest
from app.db.controls import locked


def email_key(value):
    return str(value).strip().lower()


def proof_record(db, proof, purpose=None, verified=True, lock=True):
    v = locked(db, Verification, proof.id) if lock else db.get(Verification, proof.id)
    if (
        not v
        or not hmac.compare_digest(v.flow_digest, digest(proof.flow))
        or v.consumed_at
        or v.expires_at <= now()
        or (purpose and v.purpose != purpose)
        or (verified and not v.verified_at)
    ):
        raise HTTPException(400, "인증이 없거나 만료되었습니다. 다시 인증해주세요.")
    return v
