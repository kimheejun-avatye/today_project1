"""Explicit local-only sample account. Never run against production."""
import os
if os.getenv('APP_ENV') == 'production':
    raise SystemExit('Development only')
from app.db.session import Base,engine,Session
from app.models import Member
from app.core.security import ph
from sqlalchemy import select
Base.metadata.create_all(engine)
with Session() as db:
    if not db.scalar(select(Member).where(Member.email=='demo@example.com')):
        db.add(Member(email='demo@example.com',password_hash=ph.hash('demo-password-123'),name='미리보기',nickname='미리보기'))
        db.commit()
