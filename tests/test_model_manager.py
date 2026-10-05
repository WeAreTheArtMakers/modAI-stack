import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import deps
from app.api.routes import models as model_routes
from app.api.websocket import models as model_websocket
from app.services.models.base import ModelProviderUnavailableError
from app.services.models.ollama import OllamaModelProvider, validate_model_identifier
from app.services.rag import embeddings


def run(awaitable):
    return asyncio.run(awaitable)


def test_ollama_model_list_parses_only_reported_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b", "size": 2147483648, "modified_at": "2026-01-01T12:00:00Z", "details": {"family": "llama", "parameter_size": "3.2B", "quantization_level": "Q4_K_M"}}]})

    provider = OllamaModelProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    models = run(provider.list_models())

    assert len(models) == 1
    assert models[0].name == "llama3.2:3b"
    assert models[0].provider == "ollama"
    assert models[0].size == 2147483648
    assert models[0].family == "llama"
    assert models[0].parameter_size == "3.2B"


def test_ollama_health_reports_offline_provider_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = OllamaModelProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    status = run(provider.health())

    assert status.provider == "ollama"
    assert status.ready is False


def test_ollama_pull_exposes_streamed_progress_without_downloading_a_model():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/pull"
        return httpx.Response(200, content=b'{"status":"pulling manifest"}\n{"status":"downloading","completed":50,"total":100}\n')

    async def collect():
        provider = OllamaModelProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        return [event async for event in provider.pull_model("llama3.2:3b")]

    assert run(collect()) == [
        {"status": "pulling manifest", "completed": None, "total": None},
        {"status": "downloading", "completed": 50, "total": 100},
    ]


@pytest.mark.parametrize("model", ["", "../secret", "llama;rm -rf /", "name with spaces", "a" * 201])
def test_model_identifier_rejects_paths_and_command_like_values(model):
    with pytest.raises(ValueError):
        validate_model_identifier(model)


def test_model_status_converts_provider_status_to_api_schema(monkeypatch):
    class FakeProvider:
        async def health(self):
            from app.services.models.base import ModelProviderStatus
            return ModelProviderStatus(
                provider="ollama",
                endpoint="http://ollama:11434",
                ready=True,
            )

        async def get_running_models(self):
            return ["modAIJet:latest"]

    monkeypatch.setattr(
        model_routes,
        "get_model_provider",
        lambda _name: FakeProvider(),
    )
    monkeypatch.setattr(
        model_routes,
        "get_settings",
        lambda: SimpleNamespace(
            ollama_model="modAIJet:latest"
        ),
    )
    monkeypatch.setattr(
        model_routes,
        "embedding_model_status",
        lambda: {
            "configured_model": "sentence-transformers/all-MiniLM-L6-v2",
            "source": "huggingface_cache",
            "download_allowed": False,
            "cache_available": True,
            "ready": True,
            "status": "available",
        },
    )

    status = run(
        model_routes.model_status(
            user={"sub": "1"}
        )
    )

    assert status.providers[0].provider == "ollama"
    assert status.providers[0].endpoint == "http://ollama:11434"
    assert status.providers[0].ready is True
    assert status.generation.configured_model == "modAIJet:latest"
    assert status.generation.running is True


def test_model_manager_routes_turn_unavailable_provider_into_safe_error(monkeypatch):
    class OfflineProvider:
        async def list_models(self):
            raise ModelProviderUnavailableError("offline")

    monkeypatch.setattr(model_routes, "get_model_provider", lambda _name: OfflineProvider())

    with pytest.raises(HTTPException) as error:
        run(model_routes.list_models(user={}))

    assert error.value.status_code == 503
    assert error.value.detail == "Model provider is unavailable"


def test_admin_policy_restricts_model_mutation_to_admins():
    with pytest.raises(HTTPException) as error:
        deps.ensure_admin({"role": "user"})

    assert error.value.status_code == 403
    assert deps.ensure_admin({"role": "admin", "sub": "1"})["sub"] == "1"


def test_model_pull_websocket_rejects_non_admin_before_starting_a_pull(monkeypatch):
    class FakeWebSocket:
        def __init__(self): self.messages = []; self.close_codes = []
        async def accept(self): pass
        async def send_json(self, value): self.messages.append(value)
        async def close(self, code=None): self.close_codes.append(code)
        async def receive_json(self): raise AssertionError("non-admin users must not start a pull")

    websocket = FakeWebSocket()
    async def non_admin(_ws, _scope): return {"role": "user", "workspace_membership_role": "admin"}
    monkeypatch.setattr(model_websocket, "websocket_user", non_admin)

    run(model_websocket.pull_model(websocket))

    assert websocket.messages == [{"type": "error", "data": "Admin role required"}]
    assert 1008 in websocket.close_codes


def test_platform_admin_can_start_a_model_pull_without_real_ollama(monkeypatch):
    class FakeWebSocket:
        def __init__(self): self.messages = []; self.close_codes = []
        async def accept(self): pass
        async def send_json(self, value): self.messages.append(value)
        async def close(self, code=None): self.close_codes.append(code)
        async def receive_json(self): return {"model": "qwen2.5:7b"}
    class FakeProvider:
        async def pull_model(self, _model):
            yield {"status": "downloading", "completed": 1, "total": 2}

    websocket = FakeWebSocket()
    class NoopLimiter:
        async def enforce(self, *_args): pass
        async def close(self): pass
    class FakeDb:
        def add(self, _event): pass
        async def commit(self): pass
    class FakeSession:
        async def __aenter__(self): return FakeDb()
        async def __aexit__(self, *_args): pass
    async def platform_admin(_ws, _scope): return {"sub": "1", "role": "admin", "workspace_membership_role": "user"}
    monkeypatch.setattr(model_websocket, "websocket_user", platform_admin)
    monkeypatch.setattr(model_websocket, "get_model_provider", lambda _provider: FakeProvider())
    monkeypatch.setattr(model_websocket, "RedisRateLimiter", NoopLimiter)
    monkeypatch.setattr(model_websocket, "SessionLocal", lambda: FakeSession())

    run(model_websocket.pull_model(websocket))

    assert websocket.messages == [
        {"type": "model_pull_progress", "model": "qwen2.5:7b", "status": "downloading", "completed": 1, "total": 2},
        {"type": "complete", "model": "qwen2.5:7b"},
    ]


def test_tenant_admin_cannot_delete_but_platform_admin_can_delete_non_configured_model(monkeypatch):
    class FakeProvider:
        def __init__(self): self.deleted = []
        async def delete_model(self, model): self.deleted.append(model)

    provider = FakeProvider()
    class FakeDb:
        def add(self, _event): pass
        async def commit(self): pass
    app = FastAPI()
    app.include_router(model_routes.router)
    monkeypatch.setattr(model_routes, "get_model_provider", lambda _name: provider)
    monkeypatch.setattr(model_routes, "get_settings", lambda: SimpleNamespace(ollama_model="configured:latest"))
    async def db_dependency(): yield FakeDb()
    app.dependency_overrides[model_routes.get_db] = db_dependency

    app.dependency_overrides[model_routes.current_user] = lambda: {"sub": "2", "role": "user", "workspace_membership_role": "admin"}
    with TestClient(app) as client:
        assert client.delete("/models/ollama/removable:latest").status_code == 403
    assert provider.deleted == []

    app.dependency_overrides[model_routes.current_user] = lambda: {"sub": "1", "role": "admin", "workspace_membership_role": "user"}
    with TestClient(app) as client:
        assert client.delete("/models/ollama/removable:latest").status_code == 204
    assert provider.deleted == ["removable:latest"]


def test_delete_refuses_the_configured_generation_model(monkeypatch):
    monkeypatch.setattr(model_routes, "get_settings", lambda: SimpleNamespace(ollama_model="modAIJet:latest"))

    with pytest.raises(HTTPException) as error:
        run(model_routes.delete_model("ollama", "modAIJet:latest", request=None, user={"sub": "1", "role": "admin"}, db=SimpleNamespace(add=lambda _event: None, commit=lambda: None)))

    assert error.value.status_code == 409


def test_embedding_status_reports_missing_cache_without_loading_a_model(monkeypatch, tmp_path):
    monkeypatch.setattr(embeddings, "get_settings", lambda: SimpleNamespace(embedding_model="sentence-transformers/all-MiniLM-L6-v2", embedding_cache_dir=str(tmp_path), embedding_allow_download=False))
    monkeypatch.setattr(embeddings, "get_embedding_service", lambda: SimpleNamespace(_model=None))

    status = embeddings.embedding_model_status()

    assert status == {
        "configured_model": "sentence-transformers/all-MiniLM-L6-v2",
        "source": "huggingface_cache",
        "download_allowed": False,
        "cache_available": False,
        "ready": False,
        "status": "unavailable",
    }
