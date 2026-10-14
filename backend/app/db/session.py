import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

URL = os.getenv("DATABASE_URL", "sqlite:///./diary.db")
engine = create_engine(
    URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {}
)
if URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def db_session():
    with Session() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
