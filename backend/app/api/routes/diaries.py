"""diaries API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

from datetime import date
from typing import Annotated
from fastapi import Depends, Query, Request, HTTPException
from sqlalchemy import select
from app.db.session import db_session
from app.models import Diary, now
from app.core.security import current

from fastapi import APIRouter
from app.schemas import DiaryInput
from app.api.serializers import diary_json

router = APIRouter(tags=["diaries"])


@router.get("/api/diaries")
def diaries(
    request: Request,
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    db=Depends(db_session),
):
    m, _ = current(request, db)
    return [
        diary_json(d)
        for d in db.scalars(
            select(Diary)
            .where(Diary.member_id == m.id, Diary.diary_date.startswith(month))
            .order_by(Diary.diary_date)
        )
    ]


@router.get("/api/diaries/{day}")
def get_diary(day: date, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    d = db.scalar(
        select(Diary).where(
            Diary.member_id == m.id, Diary.diary_date == day.isoformat()
        )
    )
    return (
        diary_json(d)
        if d
        else {
            "id": None,
            "date": day.isoformat(),
            "content": "",
            "emotion": "",
            "status": "DRAFT",
            "shared": False,
            "version": 0,
        }
    )


@router.put("/api/diaries/{day}")
def save_diary(day: date, data: DiaryInput, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    if data.status not in ("DRAFT", "FINAL") or (
        data.shared and data.status != "FINAL"
    ):
        raise HTTPException(400, "등록한 일기만 공유할 수 있습니다.")
    if data.shared and not (data.content.strip() or data.emotion.strip()):
        raise HTTPException(
            400, "공유할 일기 본문이나 감정을 입력해주세요. 할 일은 공유되지 않습니다."
        )
    d = db.scalar(
        select(Diary)
        .where(Diary.member_id == m.id, Diary.diary_date == day.isoformat())
        .with_for_update()
    )
    if d:
        if d.version != data.version:
            raise HTTPException(
                409,
                "다른 화면에서 수정했습니다. 작성 내용을 복사한 후 새로 불러와주세요.",
            )
        d.version += 1
    else:
        if data.version != 0:
            raise HTTPException(409, "일기 상태가 변경되었습니다.")
        d = Diary(member_id=m.id, diary_date=day.isoformat())
        db.add(d)
    d.content = data.content
    d.emotion = data.emotion
    d.status = data.status
    d.is_shared = data.shared
    d.updated_at = now()
    db.flush()
    return diary_json(d)


@router.delete("/api/diaries/{day}")
def delete_diary(day: date, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    d = db.scalar(
        select(Diary).where(
            Diary.member_id == m.id, Diary.diary_date == day.isoformat()
        )
    )
    if d:
        db.delete(d)
    return {"ok": True}
