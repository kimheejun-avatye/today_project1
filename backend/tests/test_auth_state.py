"""An unexpired, correctly signed JWT must also belong to an active login."""
import jwt
import pytest
from fastapi.testclient import TestClient

# Reuse the API suite's temporary DB and email/CAPTCHA test fixtures. These
# helpers never use the preview DB or send real authentication emails.
from test_api import client, fresh, login, post, signup, verification
from app.db.session import Session
from app.main import app
from app.models import Diary, LoginSession, now
from app.core.security import SECRET
from sqlalchemy import select


def claims(token):
    return jwt.decode(token, SECRET, algorithms=['HS256'],
                      audience='diary-web', issuer='diary-api')


@pytest.mark.parametrize('event', ['logout', 'replacement_login', 'password_reset'])
def test_copied_unexpired_tokens_rejected_after_login_ends(client, event):
    signup(client)
    login(client)
    assert client.get('/api/me').status_code == 200
    copied = {key: client.cookies.get(key) for key in ('access', 'refresh', 'csrf')}

    if event == 'logout':
        assert post(client, '/auth/logout').status_code == 200
    elif event == 'replacement_login':
        with TestClient(app, headers={'Origin': 'http://localhost:5173'}) as other:
            login(other)
            assert other.get('/api/me').status_code == 200
    else:
        proof = verification(client, purpose='PASSWORD_RESET')
        assert post(client, '/auth/password/reset',
                    {**proof, 'password': 'new-password-123'}).status_code == 200

    # The JWT itself is still correctly signed and unexpired. Rejection must
    # come from server-side login state, rather than cookie deletion or expiry.
    assert claims(copied['access'])['exp'] > now()
    with TestClient(app, headers={'Origin': 'http://localhost:5173',
                                 'X-CSRF-Token': copied['csrf']}) as replay:
        for key, value in copied.items():
            replay.cookies.set(key, value)
        assert replay.get('/api/me').status_code == 401
        assert replay.put('/api/diaries/2026-10-13', json={
            'content': 'must not be saved', 'status': 'DRAFT', 'version': 0,
        }).status_code == 401
        assert replay.post('/api/auth/refresh').status_code == 401
    with Session() as db:
        assert db.scalar(select(Diary)) is None


@pytest.mark.parametrize('missing', ['exp', 'iat', 'sid'])
def test_access_jwt_requires_expiry_issue_time_and_login_id(client, missing):
    signup(client)
    login(client)
    payload = claims(client.cookies.get('access'))
    payload.pop(missing)
    # A correctly signed token is not sufficient if required claims are absent.
    with TestClient(app) as altered:
        altered.cookies.set('access', jwt.encode(payload, SECRET, algorithm='HS256'))
        assert altered.get('/api/me').status_code == 401


@pytest.mark.parametrize('login_id', [42, ['not-a-login-id'], {'id': 'not-a-login-id'}])
def test_access_jwt_rejects_non_string_login_ids(client, login_id):
    signup(client)
    login(client)
    payload = claims(client.cookies.get('access'))
    payload['sid'] = login_id
    with TestClient(app) as altered:
        altered.cookies.set('access', jwt.encode(payload, SECRET, algorithm='HS256'))
        assert altered.get('/api/me').status_code == 401


@pytest.mark.parametrize('state', ['expired', 'revoked_at_zero'])
def test_server_login_state_overrides_valid_jwt(client, state):
    signup(client)
    login(client)
    token = client.cookies.get('access')
    payload = claims(token)
    with Session.begin() as db:
        record = db.get(LoginSession, payload['sid'])
        if state == 'expired':
            record.expires_at = now() - 1
        else:
            record.revoked_at = 0
    assert claims(token)['exp'] > now()
    assert client.get('/api/me').status_code == 401
