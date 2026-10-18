"""JWT-only access and fixed refresh lifetime regression coverage."""
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, inspect, event
from test_api import client, fresh, login, post, signup, verification
from app.db.session import Session, engine
from app.main import app
from app.models import RefreshToken, now
from app.core.security import SECRET, access


def claims(token):
    return jwt.decode(token, SECRET, algorithms=["HS256"], audience="diary-web", issuer="diary-api")


@pytest.mark.parametrize("action", ["logout", "replacement", "reset"])
def test_revoke_refresh_does_not_revoke_unexpired_access(client, action):
    signup(client);login(client)
    saved={k:client.cookies.get(k) for k in ("access","refresh","csrf")}
    if action=="logout":
        assert post(client,"/auth/logout").status_code==200
    elif action=="replacement":
        login(client)
    else:
        proof=verification(client,purpose="PASSWORD_RESET")
        assert post(client,"/auth/password/reset",{**proof,"password":"new-password-123"}).status_code==200
    with TestClient(app,headers={"Origin":"http://localhost:5173","X-CSRF-Token":saved["csrf"]}) as other:
        for k,v in saved.items():other.cookies.set(k,v)
        assert other.get("/api/me").status_code==200
        assert other.post("/api/auth/refresh").status_code==401


def test_deadlines_and_no_session_table(client):
    signup(client);login(client)
    payload=claims(client.cookies.get("access"))
    assert payload["exp"]-payload["iat"]==300
    assert "sid" not in payload
    assert "login_sessions" not in inspect(engine).get_table_names()
    with Session.begin() as db:
        token=db.scalar(select(RefreshToken))
        assert 14398 <= token.expires_at-now() <=14400
        token.expires_at=now()+30
        assert claims(access(token))["exp"]==token.expires_at
    assert post(client,"/auth/refresh").status_code==200
    with Session.begin() as db:db.scalar(select(RefreshToken)).expires_at=now()
    assert post(client,"/auth/refresh").status_code==401


def test_logout_works_with_expired_access_and_rotated_refresh(client):
    signup(client);login(client)
    old=client.cookies.get("refresh");proof=client.cookies.get("csrf")
    assert post(client,"/auth/refresh").status_code==200
    with TestClient(app,headers={"Origin":"http://localhost:5173","X-CSRF-Token":proof}) as other:
        other.cookies.set("refresh",old);other.cookies.set("csrf",proof)
        other.cookies.set("access","expired-or-invalid")
        assert other.post("/api/auth/logout").status_code==200
    assert post(client,"/auth/refresh").status_code==401


def test_csrf_bound_to_login(client):
    signup(client);login(client)
    old=client.cookies.get("csrf")
    login(client)
    client.cookies.set("csrf",old,domain="testserver.local",path="/")
    assert post(client,"/auth/refresh").status_code==403
    assert post(client,"/auth/logout").status_code==403


def test_ordinary_requests_do_not_query_auth_tables(client):
    signup(client);login(client)
    statements=[]
    def capture(conn,cursor,statement,params,context,many):statements.append(statement.lower())
    event.listen(engine,"before_cursor_execute",capture)
    try:assert client.get("/api/me").status_code==200
    finally:event.remove(engine,"before_cursor_execute",capture)
    assert not any("refresh_tokens" in s or "login_sessions" in s for s in statements)


@pytest.mark.parametrize("missing",["exp","iat","rid","sub"])
def test_required_claims(client,missing):
    signup(client);login(client)
    payload=claims(client.cookies.get("access"));payload.pop(missing)
    with TestClient(app) as other:
        other.cookies.set("access",jwt.encode(payload,SECRET,algorithm="HS256"))
        assert other.get("/api/me").status_code==401


def test_migration_preserves_data():
    from sqlalchemy import create_engine, text
    from scripts.migrate_refresh_only import migrate
    legacy=create_engine("sqlite://")
    with legacy.begin() as c:
        c.exec_driver_sql("CREATE TABLE members (id INTEGER PRIMARY KEY, name TEXT)")
        c.exec_driver_sql("INSERT INTO members VALUES (1, '보존')")
        c.exec_driver_sql("CREATE TABLE diaries (id INTEGER PRIMARY KEY, member_id INTEGER, content TEXT)")
        c.exec_driver_sql("INSERT INTO diaries VALUES (1, 1, '소중한 일기')")
        c.exec_driver_sql("CREATE TABLE login_sessions (id TEXT PRIMARY KEY)")
        c.exec_driver_sql("CREATE TABLE refresh_tokens (id TEXT PRIMARY KEY, session_id TEXT)")
        result=migrate(c)
        assert result['preserved_rows']=={'diaries':1,'members':1}
        assert migrate(c)=={'already_migrated':True}


def test_expired_access_is_rejected_then_refresh_restores_access(client):
    signup(client);login(client)
    payload=claims(client.cookies.get('access'))
    payload['exp']=now()-1
    client.cookies.set('access',jwt.encode(payload,SECRET,algorithm='HS256'),domain='testserver.local',path='/')
    assert client.get('/api/me').status_code==401
    assert post(client,'/auth/refresh').status_code==200
    assert client.get('/api/me').status_code==200


def test_logout_can_clear_expired_refresh(client):
    signup(client);login(client)
    proof=claims(client.cookies.get('csrf'))
    proof['exp']=now()-1
    client.cookies.set('csrf',jwt.encode(proof,SECRET,algorithm='HS256'),domain='testserver.local',path='/')
    with Session.begin() as db:db.scalar(select(RefreshToken)).expires_at=now()-1
    assert post(client,'/auth/logout').status_code==200
    with Session() as db:assert db.scalar(select(RefreshToken)) is None
