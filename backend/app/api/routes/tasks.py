"""tasks API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

from datetime import date
from fastapi import Depends, Request, HTTPException
from sqlalchemy import select, or_
from app.db.session import db_session
from app.models import RecurringTask, DailyTask
from app.core.security import current
from app.db.controls import locked

from fastapi import APIRouter
from app.schemas import TaskInput, ToggleTask

router = APIRouter(tags=["tasks"])


@router.post("/api/tasks")
def add_task(data: TaskInput, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    rid = None
    if data.recurring:
        r = RecurringTask(
            member_id=m.id, title=data.title, start_date=data.day.isoformat()
        )
        db.add(r)
        db.flush()
        rid = r.id
    db.add(
        DailyTask(
            member_id=m.id,
            recurring_task_id=rid,
            task_date=data.day.isoformat(),
            title=data.title,
        )
    )
    return {"ok": True}


@router.get("/api/tasks/{day}")
def tasks(day: date, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    # GET is read-only. Virtual recurring rows become persisted when checked.
    rows = list(
        db.scalars(
            select(DailyTask).where(
                DailyTask.member_id == m.id, DailyTask.task_date == day.isoformat()
            )
        )
    )
    result = [
        {
            "id": r.id,
            "recurring_id": r.recurring_task_id,
            "title": r.title,
            "completed": r.completed,
        }
        for r in rows
    ]
    ids = {r.recurring_task_id for r in rows}
    for r in db.scalars(
        select(RecurringTask).where(
            RecurringTask.member_id == m.id,
            RecurringTask.start_date <= day.isoformat(),
            or_(
                RecurringTask.end_date.is_(None),
                RecurringTask.end_date >= day.isoformat(),
            ),
        )
    ):
        if r.id not in ids:
            result.append(
                {"id": None, "recurring_id": r.id, "title": r.title, "completed": False}
            )
    return result


@router.patch("/api/tasks")
def toggle(data: ToggleTask, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    if data.id:
        row = db.get(DailyTask, data.id)
        if not row or row.member_id != m.id:
            raise HTTPException(404, "할 일을 찾을 수 없습니다.")
    else:
        r = locked(db, RecurringTask, data.recurring_id)
        if (
            not r
            or r.member_id != m.id
            or r.start_date > data.day.isoformat()
            or (r.end_date and r.end_date < data.day.isoformat())
        ):
            raise HTTPException(404, "반복 할 일을 찾을 수 없습니다.")
        row = db.scalar(
            select(DailyTask).where(
                DailyTask.recurring_task_id == r.id,
                DailyTask.task_date == data.day.isoformat(),
            )
        )
        if not row:
            row = DailyTask(
                member_id=m.id,
                recurring_task_id=r.id,
                task_date=data.day.isoformat(),
                title=r.title,
            )
            db.add(row)
    row.completed = data.completed
    return {"ok": True}


@router.delete("/api/tasks/{task_id}")
def remove_task(task_id: int, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    t = db.get(DailyTask, task_id)
    if not t or t.member_id != m.id:
        raise HTTPException(404, "할 일을 찾을 수 없습니다.")
    if t.recurring_task_id:
        raise HTTPException(400, "반복 작업은 반복 중단을 이용해주세요.")
    db.delete(t)
    return {"ok": True}


@router.post("/api/recurring/{rid}/stop")
def stop_repeat(rid: int, day: date, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    r = db.get(RecurringTask, rid)
    if not r or r.member_id != m.id:
        raise HTTPException(404, "반복을 찾을 수 없습니다.")
    if day.isoformat() < r.start_date:
        raise HTTPException(400, "시작일 이후를 선택해주세요.")
    r.end_date = day.isoformat()
    return {"ok": True}
