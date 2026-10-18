"""SMTP delivery and safe configuration status; never silently falls back to preview."""

import logging
import os
import random
import smtplib
import ssl
from email.message import EmailMessage
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def preview_enabled():
    mode = os.getenv("MAIL_MODE", "auto")
    return os.getenv("APP_ENV") != "production" and (
        mode == "preview" or (mode == "auto" and not os.getenv("SMTP_HOST"))
    )


def configuration_problem():
    if os.getenv("MAIL_MODE", "auto") not in ("auto", "smtp", "preview"):
        return "MAIL_MODE 설정을 확인해주세요."
    if preview_enabled():
        return None
    if os.getenv("MAIL_MODE") == "preview":
        return "운영에서는 메일 미리보기를 사용할 수 없습니다."
    if not os.getenv("SMTP_HOST") or not os.getenv("SMTP_FROM"):
        return "메일 서버와 발신 주소 설정이 필요합니다."
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        return "메일 서버 포트 설정을 확인해주세요."
    if bool(os.getenv("SMTP_USER")) != bool(os.getenv("SMTP_PASSWORD")):
        return "메일 발송 계정과 비밀번호를 모두 설정해주세요."
    if os.getenv("SMTP_PROVIDER") == "gmail":
        if os.getenv("SMTP_HOST") != "smtp.gmail.com" or port != 587:
            return "Gmail 연결에는 smtp.gmail.com과 587 포트를 사용해주세요."
        if not os.getenv("SMTP_USER") or not os.getenv("SMTP_PASSWORD"):
            return "Gmail 앱 비밀번호 설정이 필요합니다."
        if os.getenv("SMTP_FROM", "").lower() != os.getenv("SMTP_USER", "").lower():
            return "발신 Gmail 주소와 로그인 계정을 일치시켜주세요."
    return None


def status():
    if preview_enabled():
        return "preview"
    return "pending" if configuration_problem() else "smtp"


def connect():
    problem = configuration_problem()
    if problem or preview_enabled():
        raise HTTPException(503, problem or "실제 메일 발송 설정이 필요합니다.")
    smtp = smtplib.SMTP(
        os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=10
    )
    try:
        smtp.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USER"):
            password = os.environ["SMTP_PASSWORD"]
            if os.getenv("SMTP_PROVIDER") == "gmail":
                password = "".join(password.split())
            smtp.login(os.environ["SMTP_USER"], password)
        return smtp
    except Exception:
        smtp.close()
        raise


def retry_delay():
    # SMTP는 다음 시도 시각을 알려주지 않아 사용자 재시도가 한꺼번에 몰리지 않게 흩뜨립니다.
    return 30 + random.randint(0, 30)


def classify(error):
    """SMTP 실패를 (응답 상태, 안내 문구, 재시도 대기 초 또는 None)으로 나눕니다."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return 503, "메일 발송 설정에 문제가 있습니다. 관리자에게 문의해주세요.", None
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        code, message = next(iter(error.recipients.values()))
    elif isinstance(error, smtplib.SMTPResponseException):
        code, message = error.smtp_code, error.smtp_error
    else:
        delay = retry_delay()
        return 503, f"메일 서버에 연결하지 못했습니다. {delay}초 후 다시 시도해주세요.", delay
    text = message.decode(errors="replace") if isinstance(message, bytes) else str(message)
    # 4xx는 일시적 오류라 잠시 뒤 다시 시도할 수 있습니다.
    if code // 100 == 4:
        delay = retry_delay()
        return 503, f"메일 서버가 혼잡합니다. {delay}초 후 다시 시도해주세요.", delay
    # Gmail 하루 발송 한도 초과
    if text.lstrip().startswith("5.4.5"):
        return 503, "오늘은 인증 메일을 더 보낼 수 없습니다. 내일 다시 시도해주세요.", None
    # 받는 주소가 없거나 잘못된 경우
    if isinstance(error, smtplib.SMTPRecipientsRefused) or text.lstrip().startswith("5.1."):
        return 400, "이메일 주소를 확인해주세요.", None
    return 503, "메일을 보내지 못했습니다. 관리자에게 문의해주세요.", None


def submit(email, subject, content):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", "")
    msg["To"] = email
    msg.set_content(content)
    try:
        with connect() as smtp:
            # 수신자가 한 명이라 거절되면 반환값이 아니라 SMTPRecipientsRefused가 발생합니다.
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as error:
        status, message, delay = classify(error)
        # 수신 주소가 담긴 예외 전체 대신 코드와 서버 메시지만 남깁니다.
        if isinstance(error, smtplib.SMTPRecipientsRefused):
            detail = next(iter(error.recipients.values()))
        else:
            detail = (getattr(error, "smtp_code", None), getattr(error, "smtp_error", None))
        logger.warning("SMTP 발송 실패: %s %s", type(error).__name__, detail)
        headers = {"Retry-After": str(delay)} if delay else None
        raise HTTPException(status, message, headers=headers)


def send_code(email, code):
    if preview_enabled():
        return code
    submit(
        email,
        "하루 기록 인증번호",
        f"인증번호: {code}\n10분 이내에 입력해주세요. 직접 요청하지 않았다면 무시하세요.",
    )
