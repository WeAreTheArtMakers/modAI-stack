"""Voice assistant contract on the existing RAG path: Turkish answers, timings, warm-up."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.api.deps import current_user
from app.models.schemas import RagRequest, Source
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import RESPONSE_LANGUAGE_RULES, build_rag_prompt

ENGLISH_CONTEXT = "Every session ends after 12 hours. You can be connected from at most 2 devices at the same time."
TURKISH_QUESTION = "Aynı anda kaç cihazdan VPN'e bağlanabilirim?"


def test_turkish_response_language_is_mandatory_and_repeated_after_english_context():
    prompt = build_rag_prompt(TURKISH_QUESTION, [ENGLISH_CONTEXT], None, {"language": "tr", "tone": "professional", "response_length": "balanced"}, "tr")
    assert RESPONSE_LANGUAGE_RULES["tr"] in prompt
    assert "even when the retrieved context is in English" in prompt
    assert "Keep document names" in prompt
    # The final instruction follows the (English) context, so it is the closest to the answer.
    assert prompt.index(ENGLISH_CONTEXT) < prompt.rindex("ANSWER (Türkçe):")
    assert prompt.rstrip().endswith("ANSWER (Türkçe):")
    assert "only a greeting or thanks" in prompt
    # Grounding rules are still there.
    assert prompt.startswith("SYSTEM INSTRUCTIONS:\nYou answer only from RETRIEVED CONTEXT.")


def test_prompts_without_a_response_language_are_unchanged():
    preferences = {"language": "tr", "tone": "professional", "response_length": "balanced"}
    assert build_rag_prompt("question", ["chunk"], None, preferences) == build_rag_prompt("question", ["chunk"], None, preferences, None)
    assert "RESPONSE LANGUAGE" not in build_rag_prompt("question", ["chunk"], None, preferences)
    assert "ANSWER (" not in build_rag_prompt("question", ["chunk"])


def test_rag_request_accepts_only_known_response_languages():
    assert RagRequest(question="q", knowledge_base_ids=[1], response_language="tr").response_language == "tr"
    assert RagRequest(question="q", knowledge_base_ids=[1]).response_language is None
    assert RagRequest(question="q", knowledge_base_ids=[1]).diagnostics is False
    with pytest.raises(ValidationError):
        RagRequest(question="q", knowledge_base_ids=[1], response_language="de")


class FakeWebSocket:
    def __init__(self, request: dict):
        self.request = request
        self.messages: list[dict] = []
        self.received = 0

    async def accept(self):
        return None

    async def receive_json(self):
        self.received += 1
        if self.received == 1:
            return self.request
        raise WebSocketDisconnect()

    async def send_json(self, value):
        self.messages.append(value)

    async def close(self, code=None):
        return None


class SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


def _wire(monkeypatch, *, history=None, retrieve_calls=None, stream_calls=None, conflict_answer=None, persisted=None):
    import app.api.websocket.rag as module

    async def fake_user(_ws, _scope):
        return {"sub": "7"}

    async def resolve_scope(_db, _user, _ids):
        return [4], (SimpleNamespace(id=4), SimpleNamespace(id=3, organization_id=2), SimpleNamespace(role="user"))

    async def stored_preferences(*_args):
        return {"language": "en", "tone": "professional", "response_length": "short"}

    async def retrieve(question, **kwargs):
        retrieve_calls.append((question, kwargs))
        return SimpleNamespace(
            prompt="prompt",
            table_conflict_answer=conflict_answer,
            sources=[Source(document="vpn.md", document_id=8, chunk_index=0, score=0.8, text="secret excerpt")],
            embedding_latency_ms=12.3456,
            retrieval_latency_ms=4.0,
            liveness_latency_ms=1.0,
            prompt_latency_ms=0.2,
        )

    class Provider:
        async def stream(self, prompt, stats=None):
            stream_calls.append(prompt)
            if stats is not None:
                stats.update({"load_ms": 0.1, "prompt_eval_ms": 50.0, "prompt_eval_count": 400})
            yield "En fazla "
            yield "2 cihaz."

    async def persist(*_args, **kwargs):
        if persisted is not None:
            persisted.append(kwargs)

    monkeypatch.setattr(module, "websocket_user", fake_user)
    monkeypatch.setattr(module, "SessionLocal", lambda: SessionContext())
    monkeypatch.setattr(module, "resolve_knowledge_base_scope", resolve_scope)
    monkeypatch.setattr(module, "get_effective_assistant_preferences", stored_preferences)
    monkeypatch.setattr(module, "load_conversation_history", history or (lambda *_args: _async_value([])))
    monkeypatch.setattr(module, "retrieve_rag_context", retrieve)
    monkeypatch.setattr(module, "provider", Provider())
    monkeypatch.setattr(module, "persist_completed_turn", persist)
    return module


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_voice_request_overrides_language_for_this_request_and_reports_numeric_timings(monkeypatch):
    retrieve_calls, stream_calls = [], []
    module = _wire(monkeypatch, retrieve_calls=retrieve_calls, stream_calls=stream_calls)
    ws = FakeWebSocket({"question": TURKISH_QUESTION, "knowledge_base_ids": [4], "response_language": "tr", "diagnostics": True})

    await module.websocket_rag(ws)

    question, kwargs = retrieve_calls[0]
    assert question == TURKISH_QUESTION
    assert kwargs["response_language"] == "tr"
    assert kwargs["preferences"]["language"] == "tr"  # stored preference is "en"
    assert kwargs["knowledge_base_ids"] == [4]
    sources, *_tokens, complete = ws.messages
    assert sources["type"] == "sources" and complete["type"] == "complete"
    assert set(sources["timings"]) == {"authorization_ms", "embedding_ms", "retrieval_ms", "liveness_ms", "prompt_ms", "prompt_chars"}
    assert all(isinstance(value, (int, float)) for value in sources["timings"].values())
    assert complete["timings"]["prompt_eval_count"] == 400
    assert isinstance(complete["timings"]["first_token_ms"], float)
    # Timings carry numbers only: no question, answer or source text.
    serialized = json.dumps([sources["timings"], complete["timings"]])
    assert "VPN" not in serialized and "secret" not in serialized and "cihaz" not in serialized


@pytest.mark.asyncio
async def test_requests_without_diagnostics_keep_the_existing_event_shape(monkeypatch):
    retrieve_calls, stream_calls = [], []
    module = _wire(monkeypatch, retrieve_calls=retrieve_calls, stream_calls=stream_calls)
    ws = FakeWebSocket({"question": "question", "knowledge_base_ids": [4]})

    await module.websocket_rag(ws)

    assert retrieve_calls[0][1]["response_language"] is None
    assert retrieve_calls[0][1]["preferences"]["language"] == "en"
    assert "timings" not in ws.messages[0] and ws.messages[-1] == {"type": "complete"}


@pytest.mark.asyncio
async def test_a_voice_request_cannot_use_a_conversation_outside_its_scope(monkeypatch):
    retrieve_calls, stream_calls = [], []

    async def reject(*_args):
        raise HTTPException(400, "Conversation and selected knowledge bases must share a workspace")

    module = _wire(monkeypatch, history=reject, retrieve_calls=retrieve_calls, stream_calls=stream_calls)
    ws = FakeWebSocket({"question": TURKISH_QUESTION, "knowledge_base_ids": [4], "conversation_id": 99, "response_language": "tr", "diagnostics": True})

    await module.websocket_rag(ws)

    assert ws.messages == [{"type": "error", "data": "RAG request failed"}]
    assert retrieve_calls == [] and stream_calls == []


@pytest.mark.asyncio
async def test_an_unresolved_table_conflict_is_answered_without_the_model_and_keeps_sources(monkeypatch):
    retrieve_calls, stream_calls, persisted = [], [], []
    fixed = "Belge bu soruya kesin bir yanıt vermiyor: 5 yıl, tabloda iki satırın tam sınırında."
    module = _wire(monkeypatch, retrieve_calls=retrieve_calls, stream_calls=stream_calls, conflict_answer=fixed, persisted=persisted)
    ws = FakeWebSocket({"question": "Kıdemim tam 5 yıl", "knowledge_base_ids": [4], "conversation_id": 12, "response_language": "tr"})

    await module.websocket_rag(ws)

    assert stream_calls == []  # no model call
    sources, token, complete = ws.messages
    assert sources["type"] == "sources" and sources["data"][0]["document"] == "vpn.md"
    assert token == {"type": "token", "data": fixed} and complete == {"type": "complete"}
    assert persisted[0]["answer"] == fixed and persisted[0]["sources"][0].document == "vpn.md"


@pytest.mark.asyncio
async def test_http_query_returns_the_fixed_answer_without_the_model(monkeypatch):
    from app.api.routes import rag as rag_routes

    fixed = "Getirilen belgeler 400 km için farklı bilgi veriyor."

    class NoopLimiter:
        async def enforce(self, *_args):
            return None

        async def close(self):
            return None

    class Db:
        async def rollback(self):
            return None

    async def resolve_scope(_db, _user, _ids):
        return [4], (SimpleNamespace(id=4), SimpleNamespace(id=3, organization_id=2), SimpleNamespace(role="user"))

    async def preferences(*_args):
        return {"language": "tr", "tone": "professional", "response_length": "short"}

    async def retrieve(_question, **_kwargs):
        return SimpleNamespace(prompt="prompt", sources=[Source(document="ulasim.md", document_id=8, chunk_index=0, score=0.8)], table_conflict_answer=fixed)

    class NoModel:
        def __init__(self, *_args):
            raise AssertionError("the model must not be called")

    monkeypatch.setattr(rag_routes, "RedisRateLimiter", NoopLimiter)
    monkeypatch.setattr(rag_routes, "resolve_knowledge_base_scope", resolve_scope)
    monkeypatch.setattr(rag_routes, "get_effective_assistant_preferences", preferences)
    monkeypatch.setattr(rag_routes, "retrieve_rag_context", retrieve)
    monkeypatch.setattr(rag_routes, "OllamaProvider", NoModel)
    response = await rag_routes.query(RagRequest(question="400 km", knowledge_base_ids=[4]), request=None, user={"sub": "7"}, db=Db())
    assert response.answer == fixed and response.sources[0].document == "ulasim.md"


@pytest.mark.asyncio
async def test_ollama_stream_reports_final_timing_counters():
    lines = [
        {"response": "Merhaba", "done": False},
        {"response": "", "done": True, "load_duration": 9_000_000_000, "prompt_eval_duration": 4_000_000_000,
         "prompt_eval_count": 1665, "eval_duration": 431_000_000, "eval_count": 18, "total_duration": 13_520_000_000},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text="\n".join(json.dumps(line) for line in lines))

    provider = OllamaProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    stats: dict = {}
    tokens = [token async for token in provider.stream("prompt", stats=stats)]
    assert tokens == ["Merhaba"]
    assert stats == {"load_ms": 9000.0, "prompt_eval_ms": 4000.0, "eval_ms": 431.0, "total_ms": 13520.0, "prompt_eval_count": 1665, "eval_count": 18}


@pytest.mark.asyncio
async def test_preload_asks_ollama_to_load_the_model_without_generating():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True})

    await OllamaProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler))).preload()
    assert seen and seen[0]["prompt"] == "" and seen[0]["stream"] is False and "keep_alive" not in seen[0]


def test_warmup_requires_authentication_and_is_throttled(monkeypatch):
    from app import main
    from app.api.routes import rag as rag_routes

    calls = []

    async def preload(self):
        calls.append(1)

    class Embeddings:
        async def embed_text(self, text):
            return [0.0]

    monkeypatch.setattr(OllamaProvider, "preload", preload)
    monkeypatch.setattr(rag_routes, "get_embedding_service", lambda: Embeddings())
    monkeypatch.setitem(rag_routes._warmup, "last", float("-inf"))
    monkeypatch.setitem(rag_routes._warmup, "task", None)
    with TestClient(main.app) as client:
        assert client.post("/rag/warmup").status_code == 401
    try:
        main.app.dependency_overrides[current_user] = lambda: {"sub": "1", "role": "user"}
        with TestClient(main.app) as client:
            first = client.post("/rag/warmup")
            second = client.post("/rag/warmup")
    finally:
        main.app.dependency_overrides.clear()
    assert (first.status_code, first.json()) == (202, {"status": "warming"})
    assert (second.status_code, second.json()) == (202, {"status": "recent"})
    assert calls == [1]


@pytest.mark.asyncio
async def test_warmup_never_overlaps_a_running_load_and_closes_its_client(monkeypatch):
    import asyncio

    from app.api.routes import rag as rag_routes

    release = asyncio.Event()
    started, closed, embedded = [], [], []

    async def slow_preload(self):
        assert embedded, "the embedding model loads before the generation model"
        started.append(1)
        await release.wait()

    async def aclose(self):
        closed.append(1)

    class Embeddings:
        async def embed_text(self, text):
            embedded.append(text)
            return [0.0]

    monkeypatch.setattr(OllamaProvider, "preload", slow_preload)
    monkeypatch.setattr(httpx.AsyncClient, "aclose", aclose)
    monkeypatch.setattr(rag_routes, "get_embedding_service", lambda: Embeddings())
    monkeypatch.setitem(rag_routes._warmup, "last", float("-inf"))
    monkeypatch.setitem(rag_routes._warmup, "task", None)

    assert await rag_routes.warm_up_generation_model(user={"sub": "1"}) == {"status": "warming"}
    await asyncio.sleep(0)
    # The interval has passed but the cold load is still running: no second load request.
    rag_routes._warmup["last"] = float("-inf")
    assert await rag_routes.warm_up_generation_model(user={"sub": "1"}) == {"status": "recent"}
    release.set()
    await rag_routes._warmup["task"]
    assert started == [1] and closed == [1]
    assert len(embedded) == 1  # the embedding model is loaded as well, with a fixed text
