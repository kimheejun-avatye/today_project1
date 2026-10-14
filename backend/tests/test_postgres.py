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


def test_profile_removal_and_sql_retention(pg):
    from pathlib import Path
    scoped, factory = pg
    sql_dir = Path(__file__).resolve().parents[1] / 'sql'
    with scoped.begin() as c:
        schema = c.scalar(text('SELECT current_schema()'))
        c.execute(text('ALTER TABLE members ADD birth_date varchar(10), ADD phone varchar(30), ADD created_at integer'))
        c.execute(text('ALTER TABLE login_sessions ADD created_at integer'))
        c.execute(text("INSERT INTO members(id,email,name,nickname,password_hash,birth_date,phone,created_at) VALUES (1,'retention@example.com','private','public','hash','2000-01-01','test',1)"))
        migration = (sql_dir/'002_remove_unused_profile.sql').read_text().replace('public.', schema+'.').replace('BEGIN;', '').replace('COMMIT;', '')
        c.exec_driver_sql(migration)
        c.exec_driver_sql(migration)
        assert c.execute(text('SELECT id,name,nickname FROM members')).one() == (1,'private','public')
        assert c.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema=:schema AND ((table_name='members' AND column_name IN ('birth_date','phone','created_at')) OR (table_name='login_sessions' AND column_name='created_at'))"), {'schema':schema}) == 0
        t = now()
        c.execute(text("INSERT INTO login_sessions(id,member_id,expires_at,revoked_at,csrf_digest) VALUES ('old',1,:old,:old,'x'), ('active',1,:future,NULL,'y')"), {'old':t-90000,'future':t+1000})
        c.execute(text("INSERT INTO refresh_tokens(id,session_id,digest,expires_at,previous_id,retry_until,retry_payload) VALUES ('old1','old','old1',:old,NULL,NULL,NULL),('old2','old','old2',:old,'old1',NULL,NULL),('active1','active','active1',:old,NULL,:past,'ciphertext')"), {'old':t-90000,'past':t-10})
        c.execute(text("INSERT INTO rate_limits(key,count,started_at,blocked_until,last_sent_at) VALUES ('stale',1,:old,0,0),('blocked',1,:old,:future,0),('recent',1,:recent,0,0)"), {'old':t-90000,'future':t+1000,'recent':t})
        c.execute(text((sql_dir/'003_auth_retention.sql').read_text().replace('public.',schema+'.')))
        result = c.scalar(text(f'SELECT {schema}.haru_cleanup_auth()'))
        assert result == dict(email_verifications=0,captcha_challenges=0,rate_limits=1,login_sessions=1,refresh_tokens=2,retry_payloads=1)
        assert c.execute(text('SELECT id,retry_payload FROM refresh_tokens')).one() == ('active1',None)
        assert set(c.scalars(text('SELECT key FROM rate_limits'))) == {'blocked','recent'}
        assert c.scalar(text('SELECT count(*) FROM members')) == 1
        assert not any(c.scalar(text(f'SELECT {schema}.haru_cleanup_auth()')).values())
