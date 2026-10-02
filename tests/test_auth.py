from datetime import timedelta
import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from fastapi import HTTPException
from app.core.security import create_token, decode_token
from app.api.routes import auth
from app.models.database import Membership, User
from app.models.schemas import LoginRequest, RefreshRequest, RegisterRequest
def test_token_round_trip():
    token = create_token("1", "user", "access", timedelta(minutes=1))
    assert decode_token(token)["sub"] == "1"

@pytest.mark.asyncio
async def test_refresh_endpoint_accepts_only_refresh_tokens():
    user = User(id=1, email="user@example.com", password_hash="hash", role="user")

    class FakeDb:
        async def get(self, model, user_id):
            return user if model is User and user_id == user.id else None

    refresh_token = create_token("1", "user", "refresh", timedelta(minutes=1))
    response = await auth.refresh(RefreshRequest(refresh_token=refresh_token), FakeDb())
    assert decode_token(response.access_token)["type"] == "access"
    assert decode_token(response.refresh_token)["type"] == "refresh"

    access_token = create_token("1", "user", "access", timedelta(minutes=1))
    with pytest.raises(HTTPException) as error:
        await auth.refresh(RefreshRequest(refresh_token=access_token), FakeDb())
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
    )


@pytest.mark.asyncio
async def test_registration_creates_platform_user_and_tenant_admin_membership(monkeypatch):
    db = RegistrationDb()
    monkeypatch.setattr(auth, "get_settings", lambda: auth_settings())

    response = await auth.register(RegisterRequest(email="owner@example.com", password="correct-password"), db)

    user = next(item for item in db.items if isinstance(item, User))
    membership = next(item for item in db.items if isinstance(item, Membership))
    assert user.role == "user"
    assert membership.user_id == user.id
    assert membership.role == "admin"
    assert decode_token(response.access_token)["role"] == "user"


@pytest.mark.asyncio
async def test_registration_can_be_disabled_without_disrupting_login(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: auth_settings(allow_registration=False))
    with pytest.raises(HTTPException) as error:
        await auth.register(RegisterRequest(email="new@example.com", password="correct-password"), RegistrationDb())
    assert error.value.status_code == 403

    user = User(id=7, email="existing@example.com", password_hash=auth.hash_password("correct-password"), role="user")
    response = await auth.login(LoginRequest(email="existing@example.com", password="correct-password"), RegistrationDb(existing_user=user))
    assert decode_token(response.access_token)["sub"] == "7"
