"""config API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

import os
from app.core.security import PRODUCTION
from app.core.privacy import NOTICE
from app.services.mail import status as mail_status

from fastapi import APIRouter

router = APIRouter(tags=["config"])


@router.get("/api/config")
def config():
    state = mail_status()
    return {
        "development": not PRODUCTION,
        "mail_preview": state == "preview",
        "mail_ready": state == "smtp",
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "captcha_type": "numeric_image",
        "privacy_notice": NOTICE,
    }
