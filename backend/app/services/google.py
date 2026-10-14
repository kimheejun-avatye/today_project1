"""Google ID 토큰 검증. 브라우저가 전달한 프로필을 그대로 신뢰하지 않습니다."""

import os
from fastapi import HTTPException


def google_claim(credential):
    client = os.getenv("GOOGLE_CLIENT_ID")
    if not client:
        raise HTTPException(503, "Google 로그인 설정이 필요합니다.")
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleRequest

    try:
        claim = id_token.verify_oauth2_token(credential, GoogleRequest(), client)
    except Exception:
        raise HTTPException(401, "Google 인증을 확인할 수 없습니다.")
    if (
        not claim.get("email_verified")
        or not claim.get("sub")
        or not claim.get("email")
    ):
        raise HTTPException(401, "확인된 Google 이메일이 필요합니다.")
    return claim
