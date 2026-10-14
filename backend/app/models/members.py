from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    CheckConstraint,
)
from app.db.session import Base


class Member(Base):
    __tablename__ = "members"
    id = Column(Integer, primary_key=True)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(Text)
    name = Column(String(80), nullable=False)
    nickname = Column(String(40))
    google_subject = Column(String(255), unique=True)
    privacy_consent_version = Column(String(60))
    privacy_consented_at = Column(Integer)
    __table_args__ = (
        CheckConstraint("password_hash IS NOT NULL OR google_subject IS NOT NULL"),
    )
