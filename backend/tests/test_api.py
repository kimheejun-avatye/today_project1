import os
import tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
os.environ['APP_SECRET']='test-only-secret-not-for-production-000000'
os.environ['APP_ORIGIN']='http://localhost:5173'
os.environ['APP_ENV']='development'
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import Base,engine,Session
from app.models import Verification,RefreshToken,now
from sqlalchemy import select
import pytest
import smtplib

@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    for key in ('SMTP_HOST','SMTP_FROM','SMTP_USER','SMTP_PASSWORD','SMTP_PROVIDER','MAIL_MODE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr('app.services.captcha.new_code', lambda:'31415')

@pytest.fixture
def client():
    with TestClient(app,headers={'Origin':'http://localhost:5173'}) as c:yield c

def post(c,url,body=None):
    if url=='/auth/email/request' and 'captcha_token' not in body:
        body={**body,'captcha_token':captcha_proof(c)}
    if url=='/auth/signup' or (url=='/auth/google' and body.get('name')):
        from app.core.privacy import NOTICE
        body={'privacy_consent':True,'privacy_consent_version':NOTICE['version'],**body}
    return c.post('/api'+url,json=body,headers={'X-CSRF-Token':c.cookies.get('csrf','')})

def captcha_proof(c):
    r=post(c,'/auth/captcha',{});assert r.status_code==200,r.text
    r=post(c,'/auth/captcha/verify',{'id':r.json()['id'],'answer':'31415'});assert r.status_code==200,r.text
    return r.json()['captcha_token']

def verification(c,email='one@example.com',purpose='SIGNUP'):
    r=post(c,'/auth/email/request',{'email':email,'purpose':purpose});assert r.status_code==200,r.text
    data=r.json(); assert 'dev_code' in data,data
    proof={'id':data['id'],'flow':data['flow']}
    r=post(c,'/auth/email/verify',{**proof,'code':data['dev_code']});assert r.status_code==200,r.text
    return proof

def signup(c,email='one@example.com'):
    proof=verification(c,email)
    r=post(c,'/auth/signup',{**proof,'password':'long-password-123','name':'테스트','nickname':'하루친구',})
    assert r.status_code==201,r.text
    return proof

def login(c,email='one@example.com'):
    r=post(c,'/auth/login',{'email':email,'password':'long-password-123'});assert r.status_code==200,r.text
    return r.json()

def test_signup_one_use_and_session_revocation(client):
    proof=signup(client);login(client)
    r=post(client,'/auth/signup',{**proof,'password':'long-password-123','name':'중복','nickname':'중복친구',})
    assert r.status_code==400
    with TestClient(app,headers={'Origin':'http://localhost:5173'}) as other:
        login(other)
        assert client.get('/api/me').status_code==200
        assert post(client,'/auth/refresh').status_code==401
        assert other.get('/api/me').status_code==200
        post(other,'/auth/logout')
        assert other.get('/api/me').status_code==401

def test_expired_code_and_forged_proof(client):
    data=post(client,'/auth/email/request',{'email':'a@example.com'}).json()
    with Session() as db:
        db.get(Verification,data['id']).expires_at=now()-1;db.commit()
    assert post(client,'/auth/email/verify',{'id':data['id'],'flow':data['flow'],'code':data['dev_code']}).status_code==400
    assert post(client,'/auth/signup',{'id':data['id'],'flow':'forged','password':'long-password-123','name':'A','nickname':'A',}).status_code==400

def test_refresh_rotation_rejects_previous_token(client):
    signup(client);login(client)
    old=client.cookies.get('refresh');proof=client.cookies.get('csrf')
    with Session() as db:
        expiry=db.scalar(select(RefreshToken)).expires_at
    assert post(client,'/auth/refresh').status_code==200
    assert client.cookies.get('refresh') != old
    with TestClient(app,headers={'Origin':'http://localhost:5173','X-CSRF-Token':proof}) as stale:
        stale.cookies.set('refresh',old);stale.cookies.set('csrf',proof)
        assert stale.post('/api/auth/refresh').status_code==401
    assert post(client,'/auth/refresh').status_code==200
    with Session() as db:
        records=list(db.scalars(select(RefreshToken)))
        assert len(records)==1 and records[0].expires_at==expiry


def test_authorization_diary_conflict_and_comments(client):
    signup(client);login(client)
    body={'content':'private','emotion':'좋음','status':'FINAL','shared':False,'version':0}
    h={'X-CSRF-Token':client.cookies.get('csrf')}
    r=client.put('/api/diaries/2026-10-13',json=body,headers=h);assert r.status_code==200,r.text
    did=r.json()['id']
    assert client.put('/api/diaries/2026-10-13',json=body,headers=h).status_code==409
    with TestClient(app,headers={'Origin':'http://localhost:5173'}) as other:
        signup(other,'other@example.com');login(other,'other@example.com')
        assert other.get('/api/community').json()==[]
        assert other.get(f'/api/community/{did}/comments').status_code==404
        assert post(other,f'/community/{did}/comments',{'content':'blocked'}).status_code==404
        assert other.get('/api/diaries/2026-10-13').json()['id'] is None
    r=client.put('/api/diaries/2026-10-13',json={**body,'shared':True,'version':1},headers=h);assert r.status_code==200
    assert post(client,f'/community/{did}/comments',{'content':'hello'}).status_code==200
    assert len(client.get(f'/api/community/{did}/comments').json())==1

def test_repeat_states_are_separate_and_future_without_diary(client):
    signup(client);login(client)
    assert post(client,'/tasks',{'title':'운동','day':'2026-10-13','recurring':True}).status_code==200
    today=client.get('/api/tasks/2026-10-13').json()[0]
    r=client.patch('/api/tasks',json={'id':today['id'],'day':'2026-10-13','completed':True},headers={'X-CSRF-Token':client.cookies.get('csrf')})
    assert r.status_code==200,r.text
    tomorrow=client.get('/api/tasks/2026-10-14').json()[0]
    assert tomorrow['completed'] is False
    assert post(client,'/tasks',{'title':'병원','day':'2026-10-14','recurring':False}).status_code==200
    assert len(client.get('/api/tasks/2026-10-14').json())==2
    assert client.get('/api/diaries/2026-10-14').json()['id'] is None

def test_csrf_origin_reset_and_google_only(client):
    signup(client);login(client)
    assert client.post('/api/auth/logout').status_code==403
    assert client.post('/api/auth/logout',headers={'Origin':'https://evil.example','X-CSRF-Token':client.cookies.get('csrf')}).status_code==403
    proof=verification(client,purpose='PASSWORD_RESET')
    assert post(client,'/auth/password/reset',{**proof,'password':'new-password-123'}).status_code==200
    assert client.get('/api/me').status_code==200
    assert post(client,'/auth/refresh').status_code==401

def test_login_backoff(client):
    signup(client)
    for _ in range(5):assert post(client,'/auth/login',{'email':'one@example.com','password':'wrong'}).status_code==401
    r=post(client,'/auth/login',{'email':'one@example.com','password':'long-password-123'})
    assert r.status_code==429 and 1<=int(r.headers['retry-after'])<=30

def test_resend_limit_reports_remaining_seconds(client):
    assert post(client,'/auth/email/request',{'email':'one@example.com','purpose':'SIGNUP'}).status_code==200
    r=post(client,'/auth/email/request',{'email':'one@example.com','purpose':'SIGNUP'})
    assert r.status_code==429 and 1<=int(r.headers['retry-after'])<=60
    wrong=post(client,'/auth/email/request',{'email':'two@example.com','purpose':'SIGNUP'}).json()
    r=post(client,'/auth/email/verify',{'id':wrong['id'],'flow':wrong['flow'],'code':'000000'})
    assert r.status_code==400 and 'retry-after' not in r.headers

def test_verification_failures_survive_resend(client):
    data=post(client,'/auth/email/request',{'email':'a@example.com'}).json()
    for _ in range(5):
        assert post(client,'/auth/email/verify',{'id':data['id'],'flow':data['flow'],'code':'wrong'}).status_code==400
    from app.models import Limit
    with Session() as db:
        db.get(Limit,'mail:a@example.com:SIGNUP').last_sent_at=now()-61;db.commit()
    again=post(client,'/auth/email/request',{'email':'a@example.com'}).json()
    assert post(client,'/auth/email/verify',{'id':again['id'],'flow':again['flow'],'code':again['dev_code']}).status_code==429

def test_email_change_keeps_diary_owner_and_requires_bound_proof(client):
    signup(client);login(client)
    member_id=client.get('/api/me').json()['id']
    proof=verification(client,'changed@example.com','EMAIL_CHANGE')
    r=post(client,'/me/email',proof);assert r.status_code==200,r.text
    assert r.json()['id']==member_id and r.json()['email']=='changed@example.com'
    assert post(client,'/me/email',proof).status_code==400

def test_google_only_cannot_change_email(client,monkeypatch):
    from google.oauth2 import id_token
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client')
    monkeypatch.setattr(id_token,'verify_oauth2_token',lambda *a,**k:{'sub':'google-person','email':'google@example.com','email_verified':True})
    r=post(client,'/auth/google',{'credential':'test','intent':'signup','name':'구글','nickname':'구글친구','captcha_token':captcha_proof(client)})
    assert r.status_code==200,r.text
    assert r.json()['google_only']
    r=post(client,'/auth/email/request',{'email':'new@example.com','purpose':'EMAIL_CHANGE'})
    assert r.status_code==403

def test_google_matching_email_does_not_auto_link(client,monkeypatch):
    from google.oauth2 import id_token
    signup(client)
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client')
    monkeypatch.setattr(id_token,'verify_oauth2_token',lambda *a,**k:{'sub':'g-one','email':'one@example.com','email_verified':True})
    assert post(client,'/auth/google',{'credential':'test','intent':'signup'}).status_code==409
    assert post(client,'/auth/google',{'credential':'test','intent':'link','consent':True,'link_password':'long-password-123'}).status_code==401
    login(client)
    r=post(client,'/auth/google',{'credential':'test','intent':'link','consent':True,'link_password':'long-password-123'})
    assert r.status_code==200 and r.json()['google_linked']


def test_signup_minimal_profile(client):
    proof=verification(client)
    payload={**proof,'password':'long-password-123','name':'테스트','nickname':'하루'}
    assert post(client,'/auth/signup',payload).status_code==201
    profile=login(client)
    assert profile['nickname']=='하루'
    assert 'birth_date' not in profile and 'phone' not in profile


def test_existing_signup_email_message(client):
    signup(client)
    response=post(client,'/auth/email/request',{'email':'ONE@example.com','purpose':'SIGNUP'})
    assert response.status_code==409
    assert response.json()['detail']=='이미 가입된 이메일입니다'

def test_captcha_proof_is_required_single_use_and_expires(client):
    from app.models import CaptchaChallenge
    assert post(client,'/auth/email/request',{'email':'a@example.com','captcha_token':''}).status_code==400
    assert post(client,'/auth/email/request',{'email':'a@example.com','captcha_token':'true'}).status_code==400
    token=captcha_proof(client)
    assert post(client,'/auth/email/request',{'email':'a@example.com','captcha_token':token}).status_code==200
    assert post(client,'/auth/email/request',{'email':'b@example.com','captcha_token':token}).status_code==400
    token=captcha_proof(client)
    with Session.begin() as db:
        db.get(CaptchaChallenge,token.split(':')[0]).expires_at=now()-1
    assert post(client,'/auth/email/request',{'email':'b@example.com','captcha_token':token}).status_code==400

def test_captcha_refresh_failures_and_no_answer_leak(client):
    import base64
    response=post(client,'/auth/captcha',{});data=response.json()
    assert response.headers['Cache-Control']=='no-store'
    assert set(data)=={'id','image','audio','expires_at'}
    assert base64.b64decode(data['image'].split(',')[1]).startswith(b'\x89PNG')
    assert base64.b64decode(data['audio'].split(',')[1]).startswith(b'RIFF')
    for _ in range(5):
        assert post(client,'/auth/captcha/verify',{'id':data['id'],'answer':'00000'}).status_code==400
    assert post(client,'/auth/captcha/verify',{'id':data['id'],'answer':'31415'}).status_code==429
    token=captcha_proof(client)
    assert post(client,'/auth/captcha',{'previous_id':token.split(':')[0]}).status_code==200
    assert post(client,'/auth/email/request',{'email':'a@example.com','captcha_token':token}).status_code==400

def test_captcha_limits_survive_new_images(client):
    from app.models import Limit
    from app.core.security import digest
    with Session.begin() as db:
        db.add(Limit(key='captcha-verify:'+digest('testclient'),count=30))
    data=post(client,'/auth/captcha',{}).json()
    assert post(client,'/auth/captcha/verify',{'id':data['id'],'answer':'31415'}).status_code==429

def test_privacy_consent_is_checked_and_recorded(client):
    from app.models import Member
    from app.core.privacy import NOTICE
    proof=verification(client)
    payload={**proof,'password':'long-password-123','name':'테스트','nickname':'하루',}
    assert post(client,'/auth/signup',{**payload,'privacy_consent':False}).status_code==400
    assert post(client,'/auth/signup',{**payload,'privacy_consent_version':'stale'}).status_code==409
    assert post(client,'/auth/signup',payload).status_code==201
    with Session() as db:
        member=db.scalar(select(Member))
        assert member.privacy_consent_version==NOTICE['version'] and member.privacy_consented_at

def test_google_new_profile_and_existing_login(client,monkeypatch):
    from google.oauth2 import id_token
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-client')
    monkeypatch.setattr(id_token,'verify_oauth2_token',lambda *a,**k:{'sub':'g-new','email':'google@example.com','email_verified':True,'name':'구글'})
    assert post(client,'/auth/google/prepare',{'credential':'test'}).json()['needs_profile']
    body={'credential':'test','intent':'signup','name':'구글','captcha_token':captcha_proof(client)}
    assert post(client,'/auth/google',body).status_code==400
    body.update(nickname='구글친구')
    assert post(client,'/auth/google',{**body,'privacy_consent':False}).status_code==400
    r=post(client,'/auth/google',body)
    assert r.status_code==200 and r.json()['nickname']=='구글친구'
    assert post(client,'/auth/google/prepare',{'credential':'test'}).json()=={'needs_profile':False}
    assert post(client,'/auth/google',{'credential':'test'}).status_code==200

def test_google_login_does_not_create_a_member(client,monkeypatch):
    from app.models import Member,CaptchaChallenge
    monkeypatch.setattr('app.api.routes.google.google_claim',lambda _:{'sub':'new-google','email':'new-google@example.com','email_verified':True})
    proof=captcha_proof(client)
    r=post(client,'/auth/google',{'credential':'test','name':'새회원','nickname':'새회원','captcha_token':proof})
    assert r.status_code==403 and '회원가입' in r.json()['detail']
    with Session() as db:
        assert db.scalar(select(Member).where(Member.google_subject=='new-google')) is None
        assert db.scalar(select(RefreshToken)) is None
        assert all(c.consumed_at is None for c in db.scalars(select(CaptchaChallenge)))

def test_google_signup_cannot_log_in_an_existing_member(client,monkeypatch):
    from app.models import Member
    monkeypatch.setattr('app.api.routes.google.google_claim',lambda _:{'sub':'existing-google','email':'existing-google@example.com','email_verified':True})
    r=post(client,'/auth/google',{'credential':'test','intent':'signup','name':'기존회원','nickname':'기존회원','captcha_token':captcha_proof(client)})
    assert r.status_code==200
    assert post(client,'/auth/logout').status_code==200
    client.cookies.clear()
    assert post(client,'/auth/google',{'credential':'test','intent':'signup'}).status_code==409
    assert client.get('/api/me').status_code==401
    with Session() as db:
        assert len(list(db.scalars(select(Member))))==1
        assert len(list(db.scalars(select(RefreshToken))))==0
    assert post(client,'/auth/google',{'credential':'test','intent':'login'}).status_code==200

def test_google_link_requires_reauthentication_and_csrf(client,monkeypatch):
    from app.models import Member
    signup(client);login(client)
    monkeypatch.setattr('app.api.routes.google.google_claim',lambda _:{'sub':'link-google','email':'one@example.com','email_verified':True})
    body={'credential':'test','intent':'link','consent':True,'link_password':'long-password-123'}
    assert client.post('/api/auth/google',json=body).status_code==403
    assert post(client,'/auth/google',{**body,'link_password':'wrong'}).status_code==403
    assert post(client,'/auth/google',{**body,'consent':False}).status_code==403
    with Session() as db:
        assert db.scalar(select(Member).where(Member.email=='one@example.com')).google_subject is None
    assert post(client,'/auth/google',body).status_code==200

def test_cleanup_preserves_valid_and_recent_records(client):
    from app.models import CaptchaChallenge
    from app.maintenance import cleanup
    proof=verification(client)
    with Session.begin() as db:
        db.add(CaptchaChallenge(id='old',code_digest='x'*64,expires_at=now()-25*3600))
        db.add(CaptchaChallenge(id='recent',code_digest='x'*64,expires_at=now()-1))
        assert cleanup(db,dry_run=True)['captcha_challenges']==1
        assert db.get(CaptchaChallenge,'old')
        assert cleanup(db)['captcha_challenges']==1
    with Session() as db:
        assert db.get(CaptchaChallenge,'old') is None
        assert db.get(CaptchaChallenge,'recent') is not None
        assert db.get(Verification,proof['id']).consumed_at is None

def test_failed_member_insert_rolls_back_proof(client):
    from sqlalchemy import event
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session as SASession
    from app.models import Member
    proof=verification(client)
    payload={**proof,'password':'long-password-123','name':'테스트','nickname':'하루',}
    def fail_member(db,context):
        if any(isinstance(item,Member) for item in db.new):
            raise IntegrityError('injected test failure',None,Exception('test'))
    event.listen(SASession,'after_flush',fail_member)
    try:
        assert post(client,'/auth/signup',payload).status_code==409
    finally:
        event.remove(SASession,'after_flush',fail_member)
    with Session() as db:
        assert db.get(Verification,proof['id']).consumed_at is None
        assert db.scalar(select(Member)) is None
    assert post(client,'/auth/signup',payload).status_code==201

def test_additive_migration_keeps_existing_data():
    from sqlalchemy import create_engine,text,inspect
    from app.db.migrations import ensure_nickname
    legacy=create_engine('sqlite://')
    with legacy.begin() as c:
        c.execute(text('CREATE TABLE members (id INTEGER PRIMARY KEY, email VARCHAR(254))'))
        c.execute(text("INSERT INTO members VALUES (10, 'legacy@example.com')"))
    ensure_nickname(legacy);ensure_nickname(legacy)
    with legacy.connect() as c:
        assert c.execute(text('SELECT id,email,privacy_consented_at FROM members')).one()==(10,'legacy@example.com',None)
    assert {'nickname','privacy_consent_version','privacy_consented_at'} <= {c['name'] for c in inspect(legacy).get_columns('members')}

def test_smtp_failure_does_not_replace_previous_verification(client,monkeypatch):
    from app.models import Limit, CaptchaChallenge
    import smtplib
    original=post(client,'/auth/email/request',{'email':'a@example.com'}).json()
    token=captcha_proof(client)
    with Session.begin() as db:
        db.get(Limit,'mail:a@example.com:SIGNUP').last_sent_at=now()-61
    monkeypatch.setenv('SMTP_HOST','test.invalid')
    monkeypatch.setenv('SMTP_FROM','sender@example.com')
    class Unavailable:
        def __init__(self,*args,**kwargs):
            raise smtplib.SMTPException('test delivery unavailable')
    monkeypatch.setattr(smtplib,'SMTP',Unavailable)
    response=post(client,'/auth/email/request',{'email':'a@example.com','captcha_token':token})
    assert response.status_code==503
    with Session() as db:
        assert db.get(Verification,original['id']).consumed_at is None
        assert db.get(CaptchaChallenge,token.split(':')[0]).consumed_at is None
        assert len(list(db.scalars(select(Verification))))==1

def test_smtp_submission_uses_verified_tls_and_hides_preview(client,monkeypatch):
    import ssl
    import smtplib
    sent=[]
    monkeypatch.setenv('SMTP_HOST','test.invalid')
    monkeypatch.setenv('SMTP_FROM','sender@example.com')
    monkeypatch.delenv('SMTP_USER',raising=False)
    class Mailer:
        def __init__(self,host,port,timeout):
            assert host=='test.invalid' and timeout==10
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def starttls(self,context):
            assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        def send_message(self,message):sent.append(message)
    monkeypatch.setattr(smtplib,'SMTP',Mailer)
    response=post(client,'/auth/email/request',{'email':'a@example.com'})
    assert response.status_code==200 and 'dev_code' not in response.json()
    assert len(sent)==1 and sent[0]['To']=='a@example.com'

def test_gmail_pending_does_not_fall_back_to_preview(client,monkeypatch):
    monkeypatch.setenv('MAIL_MODE','smtp')
    monkeypatch.setenv('SMTP_PROVIDER','gmail')
    monkeypatch.setenv('SMTP_HOST','smtp.gmail.com')
    monkeypatch.setenv('SMTP_FROM','test@example.com')
    monkeypatch.setenv('SMTP_USER','test@example.com')
    settings=client.get('/api/config').json()
    assert not settings['mail_ready'] and not settings['mail_preview']
    assert not any(key.startswith('smtp_') for key in settings)
    response=post(client,'/auth/email/request',{'email':'a@example.com'})
    assert response.status_code==503 and 'dev_code' not in response.json()

def test_gmail_authenticates_and_normalizes_app_password(client,monkeypatch):
    import smtplib
    import ssl
    sent=[]
    for key,value in {'MAIL_MODE':'smtp','SMTP_PROVIDER':'gmail','SMTP_HOST':'smtp.gmail.com',
                      'SMTP_PORT':'587','SMTP_FROM':'sender@gmail.com','SMTP_USER':'sender@gmail.com',
                      'SMTP_PASSWORD':'abcd efgh ijkl mnop'}.items():monkeypatch.setenv(key,value)
    class Gmail:
        def __init__(self,host,port,timeout):assert host=='smtp.gmail.com' and port==587
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def starttls(self,context):assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        def login(self,user,password):assert user=='sender@gmail.com' and password=='abcdefghijklmnop'
        def send_message(self,message):sent.append(message);return {}
    monkeypatch.setattr(smtplib,'SMTP',Gmail)
    assert client.get('/api/config').json()['mail_ready']
    response=post(client,'/auth/email/request',{'email':'a@example.com'})
    assert response.status_code==200 and 'dev_code' not in response.json()
    assert sent[0]['From']=='sender@gmail.com' and sent[0]['To']=='a@example.com'

def test_gmail_auth_failure_never_returns_preview(client,monkeypatch):
    import smtplib
    for key,value in {'MAIL_MODE':'smtp','SMTP_PROVIDER':'gmail','SMTP_HOST':'smtp.gmail.com',
                      'SMTP_FROM':'sender@gmail.com','SMTP_USER':'sender@gmail.com',
                      'SMTP_PASSWORD':'abcdefghijklmnop'}.items():monkeypatch.setenv(key,value)
    class Denied:
        def __init__(self,*args,**kwargs):pass
        def starttls(self,context):pass
        def login(self,*args):raise smtplib.SMTPAuthenticationError(535,b'test failure')
        def close(self):pass
    monkeypatch.setattr(smtplib,'SMTP',Denied)
    response=post(client,'/auth/email/request',{'email':'a@example.com'})
    assert response.status_code==503 and 'dev_code' not in response.json()
    with Session() as db:assert db.scalar(select(Verification)) is None

def test_gmail_settings_writer_preserves_other_settings_and_permissions(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('configure_gmail',Path(__file__).resolve().parents[1]/'scripts/configure_gmail.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/'.env'
    path.write_text('APP_SECRET=test-secret\nGOOGLE_CLIENT_ID=test-client\nSMTP_USER=old@gmail.com\n# keep note\n')
    settings={'SMTP_USER':'new@gmail.com','SMTP_PASSWORD':'abcdefghijklmnop'}
    module.write_settings(path,settings);module.write_settings(path,settings)
    contents=path.read_text()
    assert 'APP_SECRET=test-secret' in contents and 'GOOGLE_CLIENT_ID=test-client' in contents and '# keep note' in contents
    assert contents.count('SMTP_USER=')==1 and path.stat().st_mode & 0o777 == 0o600


def test_public_author_uses_nickname_not_name(client):
    signup(client);login(client)
    headers={'X-CSRF-Token':client.cookies.get('csrf')}
    assert client.patch('/api/me',json={'name':'내부전용실명','nickname':'공개별명'},headers=headers).status_code==200
    response=client.put('/api/diaries/2026-10-13',json={'content':'공개 글','emotion':'좋음','status':'FINAL','shared':True,'version':0},headers=headers)
    assert response.status_code==200
    did=response.json()['id']
    assert post(client,f'/community/{did}/comments',{'content':'댓글'}).status_code==200
    for path in ('/api/community',f'/api/community/{did}/comments'):
        r=client.get(path)
        assert r.json()[0]['author']=='공개별명'
        assert '내부전용실명' not in r.text
    from app.models import Member
    with Session.begin() as db:
        db.scalar(select(Member)).nickname=None
    assert client.get('/api/community').json()[0]['author']=='익명'


def test_cleanup_expired_refresh_preserves_member(client):
    from app.models import Member
    from app.maintenance import cleanup
    signup(client);login(client)
    with Session.begin() as db:
        db.scalar(select(RefreshToken)).expires_at=now()-1
    with Session.begin() as db:
        assert cleanup(db,dry_run=True)['refresh_tokens']==1
        assert db.scalar(select(RefreshToken)) is not None
        assert cleanup(db)['refresh_tokens']==1
        assert db.scalar(select(Member)) is not None


def test_explicit_profile_drop_preserves_other_data():
    from sqlalchemy import create_engine,text,inspect
    from app.db.migrations import remove_unused_profile_columns
    legacy=create_engine('sqlite://')
    with legacy.begin() as c:
        c.execute(text('CREATE TABLE members (id INTEGER PRIMARY KEY, name TEXT, nickname TEXT, phone TEXT NOT NULL, birth_date TEXT, created_at INTEGER)'))
        c.execute(text("INSERT INTO members VALUES (1,'이름','별명','01000000000','2000-01-01',1)"))
        c.execute(text('CREATE TABLE login_sessions (id TEXT PRIMARY KEY, member_id INTEGER REFERENCES members(id), created_at INTEGER, expires_at INTEGER)'))
        c.execute(text("INSERT INTO login_sessions VALUES ('s',1,1,123)"))
    remove_unused_profile_columns(legacy);remove_unused_profile_columns(legacy)
    with legacy.connect() as c:
        assert c.execute(text('SELECT * FROM members')).one()==(1,'이름','별명')
        assert c.execute(text('SELECT * FROM login_sessions')).one()==('s',1,123)
    assert not {'phone','birth_date','created_at'} & {x['name'] for x in inspect(legacy).get_columns('members')}


def test_share_requires_content_and_exposes_diary_to_other_member(client):
    signup(client);login(client)
    headers={'X-CSRF-Token':client.cookies.get('csrf')}
    path='/api/diaries/2026-10-15'
    empty={'content':'  \n','emotion':'  ','status':'FINAL','shared':True,'version':0}
    assert client.put(path,json=empty,headers=headers).status_code==400
    assert client.get(path).json()['id'] is None
    body={**empty,'content':'오늘 작성한 일기\n두 번째 줄','emotion':'기쁨'}
    response=client.put(path,json=body,headers=headers)
    assert response.status_code==200
    did=response.json()['id']
    # Reject clearing a shared entry without altering its saved contents.
    assert client.put(path,json={**empty,'version':1},headers=headers).status_code==400
    with TestClient(app,headers={'Origin':'http://localhost:5173'}) as other:
        signup(other,'reader@example.com');login(other,'reader@example.com')
        entry=next(p for p in other.get('/api/community').json() if p['id']==did)
        assert entry['content']==body['content']
        assert entry['emotion']=='기쁨'
        assert not {'tasks','email','member_id','phone'} & entry.keys()
    # Unsharing still works, and empty private drafts remain allowed.
    response=client.put(path,json={**empty,'shared':False,'status':'DRAFT','version':1},headers=headers)
    assert response.status_code==200
    assert client.get('/api/community').json()==[]

@pytest.mark.parametrize('error,status,retry',[
    (smtplib.SMTPResponseException(421,b'4.7.0 Try again later'),503,True),
    (smtplib.SMTPServerDisconnected('closed'),503,True),
    (TimeoutError(),503,True),
    (smtplib.SMTPDataError(550,b'5.4.5 Daily user sending limit exceeded'),503,False),
    (smtplib.SMTPRecipientsRefused({'x@example.com':(550,b'5.1.1 The email account does not exist')}),400,False),
    (smtplib.SMTPAuthenticationError(535,b'5.7.8 Username and Password not accepted'),503,False),
])
def test_smtp_failures_are_classified(monkeypatch,caplog,error,status,retry):
    from app.services import mail
    from fastapi import HTTPException
    def broken():raise error
    monkeypatch.setattr(mail,'connect',broken)
    with pytest.raises(HTTPException) as raised:mail.submit('x@example.com','subject','body')
    headers=raised.value.headers or {}
    assert raised.value.status_code==status and ('Retry-After' in headers)==retry
    if retry:assert 30<=int(headers['Retry-After'])<=60 and headers['Retry-After'] in raised.value.detail
    assert 'x@example.com' not in caplog.text
