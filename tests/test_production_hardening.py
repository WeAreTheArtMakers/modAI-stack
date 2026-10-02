import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app import main
from app.services.audit import safe_metadata
from app.services.security import RedisRateLimiter, WebSocketTicketService


class FakeRedis:
    def __init__(self): self.values = {}; self.counts = {}
    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values: return False
        self.values[key] = value
        return True
    async def getdel(self, key): return self.values.pop(key, None)
    async def incr(self, key): self.counts[key] = self.counts.get(key, 0) + 1; return self.counts[key]
    async def expire(self, _key, _seconds): return True
    async def aclose(self): pass


def test_websocket_ticket_is_scoped_and_single_use():
    async def scenario():
        service = WebSocketTicketService(FakeRedis())
        ticket = await service.issue({"sub": "4", "role": "user"}, "rag")
        assert (await service.consume(ticket, "rag"))["sub"] == "4"
        with pytest.raises(HTTPException, match="expired or already used"):
            await service.consume(ticket, "rag")
    asyncio.run(scenario())


def test_websocket_ticket_rejects_wrong_scope():
    async def scenario():
        service = WebSocketTicketService(FakeRedis())
        ticket = await service.issue({"sub": "4", "role": "user"}, "rag")
        with pytest.raises(HTTPException) as error:
            await service.consume(ticket, "models_pull")
        assert error.value.status_code == 403
    asyncio.run(scenario())


def test_websocket_ticket_expiration_is_rejected():
    async def scenario():
        service = WebSocketTicketService(FakeRedis())
        with pytest.raises(HTTPException, match="expired"):
            await service.consume("expired-ticket", "rag")
    asyncio.run(scenario())


def test_redis_rate_limiter_returns_safe_429():
    async def scenario():
        limiter = RedisRateLimiter(FakeRedis())
        await limiter.enforce("login", "127.0.0.1", 1, 60)
        with pytest.raises(HTTPException) as error:
            await limiter.enforce("login", "127.0.0.1", 1, 60)
        assert error.value.status_code == 429
        assert "too many" in error.value.detail.lower()
    asyncio.run(scenario())


def test_audit_metadata_excludes_credentials_and_document_data():
    assert safe_metadata({"filename": "safe.pdf", "token": "never", "password": "never", "content": "never", "size": 10}) == {"filename": "safe.pdf", "size": 10}


def test_production_rejects_placeholder_jwt_secret(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(app_env="production", jwt_secret="change-me-in-production", refresh_cookie_secure=True))
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        main.validate_production_config()


def test_production_requires_secure_refresh_cookie(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(app_env="production", jwt_secret="a-real-secret", refresh_cookie_secure=False))
    with pytest.raises(RuntimeError, match="REFRESH_COOKIE_SECURE"):
        main.validate_production_config()


def test_request_id_is_validated_without_echoing_unsafe_input():
    assert main.REQUEST_ID.fullmatch("request-abc_123")
    assert main.REQUEST_ID.fullmatch("<script>") is None


def test_liveness_returns_request_id_and_backend_security_headers():
    with TestClient(main.app) as client:
        response = client.get("/health", headers={"X-Request-ID": "valid-request-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "valid-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
