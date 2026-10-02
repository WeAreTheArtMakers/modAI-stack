from datetime import timedelta
import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from app.core.security import create_token, decode_token
from app.api.routes import auth
from app.models.database import Membership, User
from app.models.schemas import LoginRequest, RegisterRequest, WebSocketTicketRequest


def request_for(path="/auth", headers=None):
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": path, "headers": raw_headers, "client": ("127.0.0.1", 1234)})


async def no_limit(*_args, **_kwargs): pass


class FakeRefreshSessions:
    def __init__(self): self.sessions = {}
    async def create(self, jti, user_id, _ttl_seconds):
        if jti in self.sessions: return False
        self.sessions[jti] = str(user_id)
        return True
    async def consume(self, jti, user_id):
        return self.sessions.pop(jti, None) == str(user_id)
    async def revoke(self, jti): self.sessions.pop(jti, None)
    async def close(self): pass


def install_refresh_sessions(monkeypatch):
    sessions = FakeRefreshSessions()
    monkeypatch.setattr(auth, "RefreshSessionService", lambda: sessions)
    return sessions


def test_token_round_trip():
    token = create_token("1", "user", "access", timedelta(minutes=1))
    assert decode_token(token)["sub"] == "1"

@pytest.mark.asyncio
async def test_refresh_endpoint_accepts_only_refresh_tokens(monkeypatch):
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    user = User(id=1, email="user@example.com", password_hash="hash", role="user")

    class FakeDb:
        async def get(self, model, user_id):
            return user if model is User and user_id == user.id else None

    refresh_token = await auth._issue_refresh_token(user)
    http_response = Response()
    response = await auth.refresh(request_for("/refresh"), http_response, refresh_token, FakeDb())
    assert decode_token(response.access_token)["type"] == "access"
    assert "httponly" in http_response.headers["set-cookie"].lower()

    access_token = create_token("1", "user", "access", timedelta(minutes=1))
    with pytest.raises(HTTPException) as error:
        await auth.refresh(request_for("/refresh"), Response(), access_token, FakeDb())
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        await auth.refresh(request_for("/refresh"), Response(), "not-a-token", FakeDb())
    assert error.value.status_code == 401


class RegistrationDb:
    def __init__(self, existing_user=None):
        self.existing_user = existing_user
        self.items = []
    async def scalar(self, _statement): return self.existing_user
    def add_all(self, values): self.items.extend(values)
    def add(self, value): self.items.append(value)
    async def flush(self):
        for index, item in enumerate(self.items, start=1):
            if isinstance(item, User) and item.id is None: item.id = index
    async def commit(self): pass
    async def refresh(self, _item): pass


def auth_settings(*, allow_registration=True):
    return SimpleNamespace(
        allow_registration=allow_registration,
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
        refresh_cookie_name="modai_refresh",
        refresh_cookie_secure=False,
        refresh_cookie_samesite="lax",
        rate_limit_auth_per_minute=10,
        trusted_frontend_origins="",
    )


@pytest.mark.asyncio
async def test_registration_creates_platform_user_and_tenant_admin_membership(monkeypatch):
    db = RegistrationDb()
    monkeypatch.setattr(auth, "get_settings", lambda: auth_settings())
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)

    http_response = Response()
    response = await auth.register(RegisterRequest(email="owner@example.com", password="correct-password"), request_for("/register"), http_response, db)

    user = next(item for item in db.items if isinstance(item, User))
    membership = next(item for item in db.items if isinstance(item, Membership))
    assert user.role == "user"
    assert membership.user_id == user.id
    assert membership.role == "admin"
    assert decode_token(response.access_token)["role"] == "user"
    assert "httponly" in http_response.headers["set-cookie"].lower()
    assert "refresh_token" not in response.model_dump()


@pytest.mark.asyncio
async def test_registration_can_be_disabled_without_disrupting_login(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: auth_settings(allow_registration=False))
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await auth.register(RegisterRequest(email="new@example.com", password="correct-password"), request_for("/register"), Response(), RegistrationDb())
    assert error.value.status_code == 403

    user = User(id=7, email="existing@example.com", password_hash=auth.hash_password("correct-password"), role="user")
    response = await auth.login(LoginRequest(email="existing@example.com", password="correct-password"), request_for("/login"), Response(), RegistrationDb(existing_user=user))
    assert decode_token(response.access_token)["sub"] == "7"


@pytest.mark.asyncio
async def test_login_cookie_is_http_only_and_refresh_is_not_json(monkeypatch):
    settings = auth_settings()
    settings.refresh_cookie_secure = True
    settings.refresh_cookie_samesite = "strict"
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    user = User(id=9, email="secure@example.com", password_hash=auth.hash_password("correct-password"), role="user")

    response = Response()
    tokens = await auth.login(LoginRequest(email=user.email, password="correct-password"), request_for("/login"), response, RegistrationDb(existing_user=user))

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "refresh_token" not in tokens.model_dump()


@pytest.mark.asyncio
async def test_refresh_rotates_and_old_refresh_token_cannot_be_reused(monkeypatch):
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    user = User(id=3, email="rotation@example.com", password_hash="hash", role="user")

    class FakeDb:
        async def get(self, model, user_id): return user if model is User and user_id == user.id else None

    old_token = await auth._issue_refresh_token(user)
    response = Response()
    await auth.refresh(request_for("/refresh"), response, old_token, FakeDb())
    new_token = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    assert new_token != old_token
    assert decode_token(new_token)["jti"] != decode_token(old_token)["jti"]
    with pytest.raises(HTTPException) as error:
        await auth.refresh(request_for("/refresh"), Response(), old_token, FakeDb())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session_and_clears_cookie(monkeypatch):
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    user = User(id=5, email="logout@example.com", password_hash="hash", role="user")

    class FakeDb:
        async def get(self, model, user_id): return user if model is User and user_id == user.id else None

    refresh_token = await auth._issue_refresh_token(user)
    response = Response()
    await auth.logout(request_for("/logout"), response, refresh_token)
    assert "max-age=0" in response.headers["set-cookie"].lower()
    with pytest.raises(HTTPException) as error:
        await auth.refresh(request_for("/refresh"), Response(), refresh_token, FakeDb())
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_origin_policy_accepts_same_and_trusted_origin(monkeypatch):
    settings = auth_settings()
    settings.trusted_frontend_origins = "https://console.example.test"
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    user = User(id=6, email="origin@example.com", password_hash="hash", role="user")

    class FakeDb:
        async def get(self, model, user_id): return user if model is User and user_id == user.id else None

    same_origin_token = await auth._issue_refresh_token(user)
    await auth.refresh(request_for("/refresh", {"host": "api.example.test", "origin": "http://api.example.test"}), Response(), same_origin_token, FakeDb())
    proxied_same_origin_token = await auth._issue_refresh_token(user)
    await auth.refresh(request_for("/refresh", {"host": "api.example.test", "origin": "https://api.example.test", "x-forwarded-proto": "https"}), Response(), proxied_same_origin_token, FakeDb())
    trusted_token = await auth._issue_refresh_token(user)
    await auth.refresh(request_for("/refresh", {"host": "api.example.test", "origin": "https://console.example.test"}), Response(), trusted_token, FakeDb())


@pytest.mark.asyncio
async def test_refresh_and_logout_reject_untrusted_origins(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: auth_settings())
    monkeypatch.setattr(auth, "_limit", no_limit)
    install_refresh_sessions(monkeypatch)
    untrusted = request_for("/refresh", {"host": "api.example.test", "origin": "https://attacker.example"})
    with pytest.raises(HTTPException) as error:
        await auth.refresh(untrusted, Response(), "not-used", RegistrationDb())
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        await auth.logout(request_for("/logout", {"host": "api.example.test", "origin": "https://attacker.example"}), Response(), "not-used")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_models_pull_ticket_requires_platform_admin(monkeypatch):
    monkeypatch.setattr(auth, "_limit", no_limit)
    with pytest.raises(HTTPException) as error:
        await auth.issue_websocket_ticket(
            WebSocketTicketRequest(scope="models_pull"),
            request_for("/ws-ticket"),
            {"sub": "2", "role": "user"},
            RegistrationDb(),
        )
    assert error.value.status_code == 403
