from datetime import timedelta
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from fastapi import HTTPException
from app.core.security import create_token, decode_token
from app.api.routes.auth import refresh
from app.models.database import User
from app.models.schemas import RefreshRequest
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
    response = await refresh(RefreshRequest(refresh_token=refresh_token), FakeDb())
    assert decode_token(response.access_token)["type"] == "access"
    assert decode_token(response.refresh_token)["type"] == "refresh"

    access_token = create_token("1", "user", "access", timedelta(minutes=1))
    with pytest.raises(HTTPException) as error:
        await refresh(RefreshRequest(refresh_token=access_token), FakeDb())
    assert error.value.status_code == 401
