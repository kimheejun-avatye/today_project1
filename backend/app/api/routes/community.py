"""community API. 트랜잭션의 커밋과 롤백은 db_session이 담당합니다."""

from fastapi import Depends, Request, HTTPException
from sqlalchemy import select
from app.db.session import db_session
from app.models import Member, Diary, Comment
from app.core.security import current
from app.db.controls import locked

from fastapi import APIRouter
from app.schemas import CommentInput
from app.api.serializers import diary_json

router = APIRouter(tags=["community"])


@router.get("/api/community")
def community(request: Request, db=Depends(db_session)):
    current(request, db)
    rows = db.execute(
        select(Diary, Member.nickname)
        .join(Member, Diary.member_id == Member.id)
        .where(Diary.is_shared.is_(True), Diary.status == "FINAL")
        .order_by(Diary.updated_at.desc())
        .limit(50)
    )
    return [{**diary_json(d), "author": name or "익명"} for d, name in rows]


@router.get("/api/community/{did}/comments")
def comments(did: int, request: Request, db=Depends(db_session)):
    current(request, db)
    d = db.get(Diary, did)
    if not d or not d.is_shared:
        raise HTTPException(404, "공유된 일기가 없습니다.")
    return [
        {
            "id": c.id,
            "content": c.content,
            "author": name or "익명",
            "member_id": c.member_id,
        }
        for c, name in db.execute(
            select(Comment, Member.nickname)
            .join(Member, Comment.member_id == Member.id)
            .where(Comment.diary_id == did)
            .order_by(Comment.created_at, Comment.id)
        )
    ]


@router.post("/api/community/{did}/comments")
def add_comment(did: int, data: CommentInput, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    d = locked(db, Diary, did)
    if not d or not d.is_shared:
        raise HTTPException(404, "공유된 일기가 없습니다.")
    db.add(Comment(diary_id=did, member_id=m.id, content=data.content))
    return {"ok": True}


@router.delete("/api/comments/{cid}")
def delete_comment(cid: int, request: Request, db=Depends(db_session)):
    m, _ = current(request, db)
    c = db.get(Comment, cid)
    if not c or c.member_id != m.id:
        raise HTTPException(404, "댓글을 찾을 수 없습니다.")
    db.delete(c)
    return {"ok": True}
