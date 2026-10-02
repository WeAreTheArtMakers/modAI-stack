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
from app.models.schemas import LoginRequest, RegisterRequest


def request_for(path="/auth"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("127.0.0.1", 1234)})


async def no_limit(*_args, **_kwargs): pass
def test_token_round_trip():
    token = create_token("1", "user", "access", timedelta(minutes=1))
    assert decode_token(token)["sub"] == "1"

@pytest.mark.asyncio
async def test_refresh_endpoint_accepts_only_refresh_tokens(monkeypatch):
    monkeypatch.setattr(auth, "_limit", no_limit)
    user = User(id=1, email="user@example.com", password_hash="hash", role="user")

    class FakeDb:
        async def get(self, model, user_id):
            return user if model is User and user_id == user.id else None

    refresh_token = create_token("1", "user", "refresh", timedelta(minutes=1))
    http_response = Response()
    response = await auth.refresh(request_for("/refresh"), http_response, refresh_token, FakeDb())
    assert decode_token(response.access_token)["type"] == "access"
    assert "httponly" in http_response.headers["set-cookie"].lower()

    access_token = create_token("1", "user", "access", timedelta(minutes=1))
    with pytest.raises(HTTPException) as error:
        await auth.refresh(request_for("/refresh"), Response(), access_token, FakeDb())
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
    )


@pytest.mark.asyncio
async def test_registration_creates_platform_user_and_tenant_admin_membership(monkeypatch):
    db = RegistrationDb()
    monkeypatch.setattr(auth, "get_settings", lambda: auth_settings())
    monkeypatch.setattr(auth, "_limit", no_limit)

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
    with pytest.raises(HTTPException) as error:
        await auth.register(RegisterRequest(email="new@example.com", password="correct-password"), request_for("/register"), Response(), RegistrationDb())
    assert error.value.status_code == 403

    user = User(id=7, email="existing@example.com", password_hash=auth.hash_password("correct-password"), role="user")
    response = await auth.login(LoginRequest(email="existing@example.com", password="correct-password"), request_for("/login"), Response(), RegistrationDb(existing_user=user))
    assert decode_token(response.access_token)["sub"] == "7"
