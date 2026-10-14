from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
)
from app.db.session import Base
from .common import now


class Verification(Base):
    __tablename__ = "email_verifications"
    id = Column(String(36), primary_key=True)
    member_id = Column(ForeignKey("members.id"))
    email = Column(String(254), nullable=False)
    purpose = Column(String(30), nullable=False)
    code_digest = Column(String(64), nullable=False)
    flow_digest = Column(String(64), nullable=False)
    expires_at = Column(Integer, nullable=False)
    verified_at = Column(Integer)
    consumed_at = Column(Integer)


class CaptchaChallenge(Base):
    __tablename__ = "captcha_challenges"
    id = Column(String(36), primary_key=True)
    code_digest = Column(String(64), nullable=False)
    proof_digest = Column(String(64))
    expires_at = Column(Integer, nullable=False, index=True)
    verified_at = Column(Integer)
    consumed_at = Column(Integer)
    attempts = Column(Integer, default=0, nullable=False)


class Limit(Base):
    __tablename__ = "rate_limits"
    key = Column(String(300), primary_key=True)
    count = Column(Integer, default=0, nullable=False)
    started_at = Column(Integer, default=now, nullable=False)
    blocked_until = Column(Integer, default=0, nullable=False)
    last_sent_at = Column(Integer, default=0, nullable=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id = Column(String(36), primary_key=True)
    member_id = Column(ForeignKey("members.id"), nullable=False, index=True)
    expires_at = Column(Integer, nullable=False)
    revoked_at = Column(Integer)
    refresh_revoked_at = Column(Integer)
    csrf_digest = Column(String(64), nullable=False)
    __table_args__ = (
        Index(
            "one_active_login",
            "member_id",
            unique=True,
            sqlite_where=revoked_at.is_(None),
            postgresql_where=revoked_at.is_(None),
        ),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String(36), primary_key=True)
    session_id = Column(ForeignKey("login_sessions.id"), nullable=False, index=True)
    digest = Column(String(64), nullable=False, unique=True)
    previous_id = Column(ForeignKey("refresh_tokens.id"), unique=True)
    expires_at = Column(Integer, nullable=False)
    rotated_at = Column(Integer)
    retry_until = Column(Integer)
    retry_payload = Column(Text)
