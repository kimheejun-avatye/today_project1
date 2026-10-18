from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
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


class RefreshToken(Base):
    # 로그인 세션 테이블 없이 회원과 직접 연결한다. 회원당 현재 Refresh 한 건만 유지한다.
    # 교체 시 digest만 바꾸고, 로그아웃 시 행을 삭제하므로 종료 상태 컬럼은 두지 않는다.
    __tablename__ = "refresh_tokens"
    id = Column(String(36), primary_key=True)
    member_id = Column(ForeignKey("members.id"), nullable=False, unique=True)
    digest = Column(String(64), nullable=False, unique=True)
    expires_at = Column(Integer, nullable=False, index=True)
