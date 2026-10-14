"""SMTP delivery and safe configuration status; never silently falls back to preview."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from fastapi import HTTPException


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


def submit(email, subject, content):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", "")
    msg["To"] = email
    msg.set_content(content)
    try:
        with connect() as smtp:
            refused = smtp.send_message(msg)
            if refused:
                raise HTTPException(503, "메일 서비스가 수신 주소를 거절했습니다.")
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            503, "메일 발송 계정 인증에 실패했습니다. 발송 설정을 확인해주세요."
        )
    except (OSError, smtplib.SMTPException):
        raise HTTPException(
            503, "메일 발송 결과를 확인하지 못했습니다. 잠시 후 재요청하세요."
        )


def send_code(email, code):
    if preview_enabled():
        return code
    submit(
        email,
        "하루 기록 인증번호",
        f"인증번호: {code}\n10분 이내에 입력해주세요. 직접 요청하지 않았다면 무시하세요.",
    )
