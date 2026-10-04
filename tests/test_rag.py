from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.rag import pipeline
from app.services.rag.chunker import chunk_text
from app.services.rag.pipeline import build_rag_prompt


def test_chunking_and_prompt_boundary():
    chunks = chunk_text("one two three four five", 3, 1)
    prompt = build_rag_prompt("what?", chunks)
    assert len(chunks) == 2 and "SYSTEM INSTRUCTIONS" in prompt and "untrusted" in prompt

def test_chunk_text_empty_input_returns_no_chunks():
    assert chunk_text("", 3, 1) == []

def test_chunk_text_preserves_overlap_between_chunks():
    assert chunk_text("one two three four five six", 3, 1) == [
        "one two three",
        "three four five",
        "five six",
    ]

def test_chunk_text_rejects_invalid_parameters():
    for size, overlap in [(0, 0), (-1, 0), (3, -1), (3, 3), (3, 4)]:
        try:
            chunk_text("one two", size, overlap)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid chunk parameters should raise ValueError")


def test_rag_top_k_defaults_to_three_without_an_environment_override(monkeypatch):
    monkeypatch.delenv("RAG_TOP_K", raising=False)
    assert Settings(_env_file=None).rag_top_k == 3


def test_rag_top_k_allows_an_environment_override(monkeypatch):
    monkeypatch.setenv("RAG_TOP_K", "7")
    assert Settings(_env_file=None).rag_top_k == 7


@pytest.mark.asyncio
async def test_rag_pipeline_uses_configured_top_k_when_no_limit_is_supplied(monkeypatch):
    observed: dict[str, object] = {}

    class FakeEmbeddingService:
        async def embed_text(self, _text: str):
            return [0.1]

    class FakeQdrantService:
        async def search(self, **kwargs):
            observed.update(kwargs)
            return []

    monkeypatch.setattr(pipeline, "get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(pipeline, "qdrant_service", FakeQdrantService())
    monkeypatch.setattr(pipeline, "get_settings", lambda: SimpleNamespace(rag_top_k=3))

    context = await pipeline.retrieve_rag_context(
        "question", organization_id=1, workspace_id=2, knowledge_base_ids=[3]
    )

    assert observed["limit"] == 3
    assert observed["organization_id"] == 1
    assert observed["workspace_id"] == 2
    assert observed["knowledge_base_ids"] == [3]
    assert context.sources == []
