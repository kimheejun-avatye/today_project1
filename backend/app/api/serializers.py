"""DB 객체에서 공개 API 응답에 필요한 필드만 선택합니다."""


def member_json(m):
    return {
        "id": m.id,
        "email": m.email,
        "name": m.name,
        "nickname": m.nickname,
        "google_only": not bool(m.password_hash),
        "google_linked": bool(m.google_subject),
    }


def diary_json(d):
    return {
        "id": d.id,
        "date": d.diary_date,
        "content": d.content,
        "emotion": d.emotion,
        "status": d.status,
        "shared": d.is_shared,
        "version": d.version,
    }
