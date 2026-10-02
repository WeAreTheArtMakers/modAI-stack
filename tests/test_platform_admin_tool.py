import asyncio

import pytest

from app.models.database import User
from app.tools import create_platform_admin
from app.core.security import verify_password


class FakeDb:
    def __init__(self, user=None):
        self.user = user
        self.added = []
    async def scalar(self, _statement): return self.user
    def add(self, user):
        self.added.append(user)
        self.user = user
    async def commit(self): pass
    async def refresh(self, _user): pass


class FakeSessionFactory:
    def __init__(self, db): self.db = db
    def __call__(self): return self
    async def __aenter__(self): return self.db
    async def __aexit__(self, *_args): pass


def test_platform_admin_bootstrap_promotes_existing_user_without_printing_credentials(monkeypatch):
    user = User(id=1, email="owner@example.com", password_hash="preserved", role="user")
    monkeypatch.setattr(create_platform_admin, "SessionLocal", FakeSessionFactory(FakeDb(user)))

    promoted, created = asyncio.run(create_platform_admin.promote_platform_admin("OWNER@example.com"))

    assert created is False
    assert promoted.role == "admin"
    assert promoted.password_hash == "preserved"


def test_platform_admin_bootstrap_requires_explicit_create_and_interactive_password(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(create_platform_admin, "SessionLocal", FakeSessionFactory(db))

    with pytest.raises(ValueError, match="--create"):
        asyncio.run(create_platform_admin.promote_platform_admin("new@example.com"))
    created, was_created = asyncio.run(create_platform_admin.promote_platform_admin("new@example.com", create=True, password="safe-password"))

    assert was_created is True
    assert created.role == "admin"
    assert verify_password("safe-password", created.password_hash)
