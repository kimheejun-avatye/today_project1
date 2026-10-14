from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    ForeignKeyConstraint,
)
from app.db.session import Base


class RecurringTask(Base):
    __tablename__ = "recurring_tasks"
    id = Column(Integer, primary_key=True)
    member_id = Column(ForeignKey("members.id"), nullable=False)
    title = Column(String(200), nullable=False)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10))
    __table_args__ = (UniqueConstraint("id", "member_id"),)


class DailyTask(Base):
    __tablename__ = "daily_tasks"
    id = Column(Integer, primary_key=True)
    member_id = Column(ForeignKey("members.id"), nullable=False, index=True)
    recurring_task_id = Column(Integer)
    task_date = Column(String(10), nullable=False)
    title = Column(String(200), nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    __table_args__ = (
        UniqueConstraint("recurring_task_id", "task_date"),
        ForeignKeyConstraint(
            ["recurring_task_id", "member_id"],
            ["recurring_tasks.id", "recurring_tasks.member_id"],
        ),
    )
