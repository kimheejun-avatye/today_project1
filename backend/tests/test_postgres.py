"""Run through scripts/check_postgres.py against a disposable real server."""
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session as SASession, sessionmaker
from sqlalchemy.exc import IntegrityError
from app import main
from app.services import verification
from app.db.session import Base, db_session, engine
from app.db.migrations import ensure_nickname
from app.models import Member, Verification, now
from app.core.privacy import NOTICE
from app.core.security import digest

pytestmark = pytest.mark.skipif(os.getenv('HARU_TEMP_POSTGRES') != '1', reason='Use scripts/check_postgres.py for a disposable PostgreSQL server')

@pytest.fixture
def pg(monkeypatch):
    assert engine.dialect.name == 'postgresql'
    schema = 'haru_test_' + uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(text(f'CREATE SCHEMA {schema}'))
    scoped = create_engine(str(engine.url), connect_args={'options': f'-csearch_path={schema}'})
    factory = sessionmaker(scoped, expire_on_commit=False)
    Base.metadata.create_all(scoped)
    def sessions():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    main.app.dependency_overrides[db_session] = sessions
    monkeypatch.delenv('SMTP_HOST', raising=False)
    try:
        yield scoped, factory
    finally:
        main.app.dependency_overrides.pop(db_session, None)
        scoped.dispose()
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA {schema} CASCADE'))

def proof(factory, email):
    identity, flow = str(uuid.uuid4()), uuid.uuid4().hex
    with factory.begin() as db:
        db.add(Verification(id=identity, email=email, purpose='SIGNUP', code_digest=digest('test'),
                            flow_digest=digest(flow), expires_at=now()+600, verified_at=now()))
    return {'id': identity, 'flow': flow, 'password': 'test-password-123', 'name': '테스트',
            'nickname': '하루',  
            'privacy_consent': True, 'privacy_consent_version': NOTICE['version']}

def send(body):
    with TestClient(main.app, headers={'Origin': 'http://localhost:5173'}) as c:
        return c.post('/api/auth/signup', json=body)

def test_real_row_lock_wait_and_independent_signup(pg, monkeypatch):
    _, factory = pg
    shared = proof(factory, 'shared@example.com')
    independent = proof(factory, 'independent@example.com')
    acquired, waiting, release = threading.Event(), threading.Event(), threading.Event()
    original = verification.locked
    first = True
    mutex = threading.Lock()
    def held(db, model, identity):
        nonlocal first
        is_first = False
        if model is Verification and identity == shared['id']:
            with mutex:
                is_first, first = first, False
            if not is_first:
                waiting.set()
        row = original(db, model, identity)
        if is_first:
            acquired.set()
            assert release.wait(10), 'Test did not release the held row lock'
        return row
    monkeypatch.setattr(verification, 'locked', held)
    with ThreadPoolExecutor(max_workers=3) as pool:
        a = pool.submit(send, shared)
        try:
            assert acquired.wait(5)
            b = pool.submit(send, shared)
            assert waiting.wait(5)
            independent_result = pool.submit(send, independent).result(timeout=5)
            assert independent_result.status_code == 201, independent_result.text
            assert not b.done(), 'Second request must wait for the first transaction'
            with engine.connect() as c:
                assert c.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND datname=current_database()")) >= 1
        finally:
            release.set()
        assert a.result(timeout=5).status_code == 201
        assert b.result(timeout=5).status_code == 400
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Member).where(Member.email=='shared@example.com')) == 1
        assert db.get(Verification, shared['id']).consumed_at

def test_member_failure_rolls_back_authentication_use(pg):
    _, factory = pg
    payload = proof(factory, 'rollback@example.com')
    def reject(db, context):
        if any(isinstance(item, Member) for item in db.new):
            raise IntegrityError('injected insert failure', None, Exception('test'))
    event.listen(SASession, 'after_flush', reject)
    try:
        assert send(payload).status_code == 409
    finally:
        event.remove(SASession, 'after_flush', reject)
    with factory() as db:
        assert db.get(Verification, payload['id']).consumed_at is None
        assert db.scalar(select(func.count()).select_from(Member)) == 0
    assert send(payload).status_code == 201

def test_distinct_proofs_cannot_duplicate_email(pg):
    _, factory = pg
    first = proof(factory, 'unique@example.com')
    second = proof(factory, 'unique@example.com')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, (first, second)))
    assert sorted(r.status_code for r in results) == [201, 409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Member)) == 1
        assert sum(bool(db.get(Verification, p['id']).consumed_at) for p in (first, second)) == 1

def test_postgres_legacy_member_upgrade(pg):
    scoped, _ = pg
    # Separate legacy table fixture with all dependent tables removed in this test schema.
    Base.metadata.drop_all(scoped)
    with scoped.begin() as c:
        c.execute(text('CREATE TABLE members (id INTEGER PRIMARY KEY, email VARCHAR(254))'))
        c.execute(text("INSERT INTO members VALUES (10, 'legacy@example.com')"))
    ensure_nickname(scoped)
    ensure_nickname(scoped)
    with scoped.connect() as c:
        assert c.execute(text('SELECT id,email,privacy_consented_at FROM members')).one() == (10, 'legacy@example.com', None)


def test_refresh_migration_and_retention(pg):
    from pathlib import Path
    from scripts.migrate_refresh_only import migrate
    scoped, factory = pg
    with scoped.begin() as c:
        schema = c.scalar(text("SELECT current_schema()"))
        c.exec_driver_sql("DROP TABLE refresh_tokens")
        c.exec_driver_sql("CREATE TABLE login_sessions(id TEXT PRIMARY KEY, member_id INTEGER REFERENCES members(id))")
        c.exec_driver_sql("CREATE TABLE refresh_tokens(id TEXT PRIMARY KEY, session_id TEXT REFERENCES login_sessions(id))")
        c.exec_driver_sql("INSERT INTO members(id,email,name,nickname,password_hash) VALUES (1,'keep@example.com','keep','keep','test-hash')")
        # Run the same SQL as production, within this isolated schema.
        sql_dir=Path(__file__).resolve().parents[1]/'sql'
        c.execute(text((sql_dir/'006_refresh_only.sql').read_text().replace('public.',schema+'.')))
        c.execute(text((sql_dir/'003_auth_retention.sql').read_text().replace('public.',schema+'.')))
        assert c.scalar(text('SELECT count(*) FROM members'))==1
        c.execute(text("INSERT INTO refresh_tokens VALUES ('old',1,'hash',:expired)"),{'expired':now()-1})
        result=c.scalar(text(f'SELECT {schema}.haru_cleanup_auth()'))
        assert result['refresh_tokens']==1
        assert c.scalar(text('SELECT count(*) FROM members'))==1
        assert c.scalar(text("SELECT to_regclass(:name)"),{'name':schema+'.login_sessions'}) is None


def test_concurrent_refresh_and_logout_cannot_restore_record(pg):
    from app.models import RefreshToken
    from app.services.refresh import rotate_refresh_token, revoke_refresh_token
    from app.core.security import signed_claims, SECRET
    from starlette.requests import Request
    import jwt
    scoped,factory=pg
    identity=str(uuid.uuid4());raw=identity+'.secret'
    with factory.begin() as db:
        member=Member(email='race@example.com',name='race',nickname='race',password_hash='test-hash')
        db.add(member);db.flush();mid=member.id
        db.add(RefreshToken(id=identity,member_id=mid,digest=digest(raw),expires_at=now()+14400))
    proof=jwt.encode(signed_claims('csrf',mid,identity,now()+14400),SECRET,algorithm='HS256')
    request=Request({'type':'http','headers':[(b'x-csrf-token',proof.encode()),(b'cookie',('csrf='+proof).encode())]})
    acquired=threading.Event();release=threading.Event()
    def rotate():
        with factory() as db:
            db.execute(select(RefreshToken).where(RefreshToken.id==identity).with_for_update()).scalar_one()
            acquired.set();assert release.wait(5)
            return rotate_refresh_token(db,raw,request)
    def logout():
        with factory() as db:revoke_refresh_token(db,raw,request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(rotate)
        assert acquired.wait(5)
        second=pool.submit(logout)
        release.set()
        first.result(timeout=5);second.result(timeout=5)
    with factory() as db:assert db.get(RefreshToken,identity) is None


def test_two_refresh_requests_only_one_can_rotate(pg):
    from app.models import RefreshToken
    from app.services.refresh import rotate_refresh_token
    from app.core.security import signed_claims, SECRET
    from starlette.requests import Request
    from fastapi import HTTPException
    import jwt
    _,factory=pg
    identity=str(uuid.uuid4());raw=identity+'.secret'
    with factory.begin() as db:
        member=Member(email='double@example.com',name='double',nickname='double',password_hash='hash')
        db.add(member);db.flush();mid=member.id
        db.add(RefreshToken(id=identity,member_id=mid,digest=digest(raw),expires_at=now()+14400))
    proof=jwt.encode(signed_claims('csrf',mid,identity,now()+14400),SECRET,algorithm='HS256')
    request=Request({'type':'http','headers':[(b'x-csrf-token',proof.encode()),(b'cookie',('csrf='+proof).encode())]})
    barrier=threading.Barrier(2)
    def run():
        with factory() as db:
            barrier.wait(timeout=5)
            try:rotate_refresh_token(db,raw,request);return 200
            except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _:run(),range(2)))==[200,401]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RefreshToken))==1


def test_access_member_lookup_on_postgres(pg):
    from app.core.security import access, current
    from types import SimpleNamespace
    from starlette.requests import Request
    _,factory=pg
    with factory.begin() as db:
        member=Member(email='access@example.com',name='access',nickname='access',password_hash='hash')
        db.add(member);db.flush();mid=member.id
    raw=access(SimpleNamespace(member_id=mid,id=str(uuid.uuid4()),expires_at=now()+14400))
    request=Request({'type':'http','method':'GET','headers':[(b'cookie',('access='+raw).encode())]})
    with factory() as db:
        assert current(request,db)[0].id==mid
