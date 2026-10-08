import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app import main
from app.api.deps import current_user
from app.api.routes import health
from app.db.session import get_db
from app.services.audit import safe_metadata
from app.services.security import RedisRateLimiter, WebSocketTicketService


class FakeRedis:
    def __init__(self): self.values = {}; self.counts = {}; self.eval_calls = []; self.set_calls = []
    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values: return False
        self.set_calls.append((key, value, ex, nx))
        self.values[key] = value
        return True
    async def getdel(self, key): return self.values.pop(key, None)
    async def delete(self, key): self.values.pop(key, None)
    async def eval(self, script, key_count, key, window_seconds):
        self.eval_calls.append((script, key_count, key, window_seconds))
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]
    async def aclose(self): pass


def test_websocket_ticket_is_scoped_and_single_use():
    async def scenario():
        service = WebSocketTicketService(FakeRedis())
        ticket = await service.issue({"sub": "4", "role": "user"}, "rag")
        assert (await service.consume(ticket, "rag"))["sub"] == "4"
        with pytest.raises(HTTPException, match="expired or already used"):
            await service.consume(ticket, "rag")
    asyncio.run(scenario())


def test_websocket_tickets_are_random_and_preserve_indexing_workspace_scope():
    async def scenario():
        redis = FakeRedis()
        service = WebSocketTicketService(redis)
        first = await service.issue({"sub": "4", "role": "user"}, "indexing", workspace_id=12)
        second = await service.issue({"sub": "4", "role": "user"}, "indexing", workspace_id=12)
        assert first != second and len(first) >= 40
        assert all(call[2] == 60 for call in redis.set_calls)
        assert (await service.consume(first, "indexing"))["workspace_id"] == 12
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


def test_normal_access_jwt_is_not_a_websocket_ticket():
    from datetime import timedelta
    from app.core.security import create_token

    async def scenario():
        service = WebSocketTicketService(FakeRedis())
        with pytest.raises(HTTPException) as error:
            await service.consume(create_token("4", "user", "access", timedelta(minutes=1)), "rag")
        assert error.value.status_code == 401
    asyncio.run(scenario())


def test_redis_rate_limiter_returns_safe_429():
    async def scenario():
        redis = FakeRedis()
        limiter = RedisRateLimiter(redis)
        await limiter.enforce("login", "127.0.0.1", 1, 60)
        assert len(redis.eval_calls) == 1
        assert redis.eval_calls[0][1:] == (1, "modai:rate-limit:login:127.0.0.1", 60)
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
    # Voice assistant: microphone for this origin only; WebAssembly compilation but no JS eval.
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(self), geolocation=()"
    assert "script-src 'self' 'wasm-unsafe-eval';" in response.headers["Content-Security-Policy"]
    assert "'unsafe-eval'" not in response.headers["Content-Security-Policy"].replace("'wasm-unsafe-eval'", "")


def test_public_version_endpoint_returns_build_sha_without_caching(monkeypatch):
    monkeypatch.setattr(health, "get_settings", lambda: SimpleNamespace(build_sha="a" * 40))
    with TestClient(main.app) as client:
        response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"build_sha": "a" * 40}
    assert response.headers["cache-control"] == "no-store"


def test_build_sha_setting_reads_environment_and_defaults_for_development(monkeypatch):
    from app.core.config import Settings

    monkeypatch.delenv("BUILD_SHA", raising=False)
    assert Settings(_env_file=None).build_sha == "development"
    monkeypatch.setenv("BUILD_SHA", "b" * 40)
    assert Settings(_env_file=None).build_sha == "b" * 40


def test_platform_admin_endpoints_are_not_granted_to_tenant_admins():
    class EmptyDb:
        async def scalars(self, _statement):
            class Result:
                def all(self): return []
            return Result()

    async def empty_db():
        yield EmptyDb()

    try:
        main.app.dependency_overrides[current_user] = lambda: {"sub": "1", "role": "user"}
        with TestClient(main.app) as client:
            assert client.get("/audit").status_code == 403
            assert client.get("/metrics").status_code == 403

        main.app.dependency_overrides[get_db] = empty_db
        main.app.dependency_overrides[current_user] = lambda: {"sub": "1", "role": "admin"}
        with TestClient(main.app) as client:
            assert client.get("/audit").status_code == 200
            assert client.get("/metrics").status_code == 200
    finally:
        main.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readiness_reports_dependency_failure_while_liveness_stays_alive(monkeypatch):
    class BrokenEngine:
        def connect(self): raise RuntimeError("database unavailable")

    class BrokenQueue:
        def __init__(self): self.client = self
        async def ping(self): raise RuntimeError("redis unavailable")
        async def close(self): pass

    class BrokenHttpClient:
        def __init__(self, *_args, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def get(self, _url): raise health.httpx.ConnectError("qdrant unavailable")

    class BrokenOllama:
        async def health_check(self): return False

    monkeypatch.setattr(health, "engine", BrokenEngine())
    monkeypatch.setattr(health, "RedisIndexQueue", BrokenQueue)
    monkeypatch.setattr(health.httpx, "AsyncClient", BrokenHttpClient)
    monkeypatch.setattr(health, "OllamaProvider", BrokenOllama)
    monkeypatch.setattr(health, "embedding_model_status", lambda: {"ready": False})

    readiness = await health.ready()
    assert readiness["ready"] is False
    assert readiness["dependencies"] == {"postgres": False, "redis": False, "qdrant": False}
    assert await health.health() == {"status": "ok"}
