"""FastAPI 진입점: 환경 로딩, 앱 수명주기, 공통 응답 처리, 라우터 등록."""

from app.core import config as environment  # noqa: F401 -- DB/보안 모듈보다 먼저 환경 설정을 읽습니다.
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from app.db.session import Base, engine
from app.db.migrations import ensure_nickname
from app.core.security import PRODUCTION, ORIGIN
from app.services.mail import configuration_problem
from app.api.routes import auth, community, config, diaries, google, members, tasks


@asynccontextmanager
async def lifespan(app):
    if PRODUCTION and (
        not os.getenv("SMTP_HOST")
        or not os.getenv("SMTP_FROM")
        or not str(engine.url).startswith("postgresql")
    ):
        raise RuntimeError("Production requires PostgreSQL and SMTP configuration")
    if PRODUCTION and configuration_problem():
        raise RuntimeError(configuration_problem())
    Base.metadata.create_all(engine)
    ensure_nickname(engine)
    yield


app = FastAPI(title="하루 기록 API", lifespan=lifespan)


@app.middleware("http")
async def origin_guard(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith(
        "/api"
    ):
        if request.headers.get("origin") != ORIGIN:
            return JSONResponse(
                {"detail": "허용하지 않은 출처입니다."}, status_code=403
            )
    result = await call_next(request)
    result.headers["Cache-Control"] = "no-store"
    result.headers["X-Content-Type-Options"] = "nosniff"
    return result


@app.exception_handler(IntegrityError)
async def conflict_handler(request, exc):
    return JSONResponse(
        {"detail": "이미 처리되었거나 중복된 정보입니다. 다시 불러와 주세요."},
        status_code=409,
    )


for router_module in (config, auth, google, members, diaries, tasks, community):
    app.include_router(router_module.router)
