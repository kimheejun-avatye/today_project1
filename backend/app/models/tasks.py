from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
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
    __table_args__ = (
        UniqueConstraint("id", "member_id"),
        CheckConstraint("length(start_date) = 10 AND substr(start_date, 5, 1) = '-' AND substr(start_date, 8, 1) = '-'"),
        CheckConstraint("end_date IS NULL OR (length(end_date) = 10 AND substr(end_date, 5, 1) = '-' AND substr(end_date, 8, 1) = '-')"),
    )


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
        CheckConstraint("length(task_date) = 10 AND substr(task_date, 5, 1) = '-' AND substr(task_date, 8, 1) = '-'"),
        ForeignKeyConstraint(
            ["recurring_task_id", "member_id"],
            ["recurring_tasks.id", "recurring_tasks.member_id"],
        ),
    )
