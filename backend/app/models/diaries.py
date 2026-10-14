from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
)
from app.db.session import Base
from .common import now


class Diary(Base):
    __tablename__ = "diaries"
    id = Column(Integer, primary_key=True)
    member_id = Column(ForeignKey("members.id"), nullable=False)
    diary_date = Column(String(10), nullable=False)
    content = Column(Text, default="", nullable=False)
    emotion = Column(String(40), default="", nullable=False)
    status = Column(String(10), default="DRAFT", nullable=False)
    is_shared = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    updated_at = Column(Integer, default=now, nullable=False)
    __table_args__ = (
        UniqueConstraint("member_id", "diary_date"),
        CheckConstraint("status IN ('DRAFT','FINAL')"),
        CheckConstraint("NOT is_shared OR status = 'FINAL'"),
    )


class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    diary_id = Column(
        ForeignKey("diaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id = Column(ForeignKey("members.id"), nullable=False)
    content = Column(String(2000), nullable=False)
    created_at = Column(Integer, default=now, nullable=False)
