import asyncio
import sys
from types import SimpleNamespace

import pytest

from app.services.rag import embeddings


class FakeVectors:
    def __init__(self, vectors):
        self.vectors = vectors

    def tolist(self):
        return self.vectors


class FakeEmbeddingModel:
    def encode(self, texts, **_kwargs):
        return FakeVectors([[float(len(text))] for text in texts])


def test_injected_embedding_model_works_without_loading_sentence_transformers():
    service = embeddings.EmbeddingService(model=FakeEmbeddingModel())

    assert asyncio.run(service.embed_text("abc")) == [3.0]


def test_local_embedding_model_path_is_accepted_without_network(monkeypatch, tmp_path):
    local_model = tmp_path / "all-MiniLM-L6-v2"
    local_model.mkdir()
    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            calls.append((model_name_or_path, kwargs))

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: SimpleNamespace(
            embedding_model=str(local_model),
            embedding_cache_dir=str(tmp_path / "cache"),
            embedding_allow_download=False,
        ),
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeSentenceTransformer))

    embeddings.EmbeddingService()._get_model()

    assert calls == [
        (
            str(local_model),
            {"cache_folder": str(tmp_path / "cache"), "local_files_only": True},
        )
    ]


def test_unavailable_embedding_model_has_a_clear_cache_only_error(monkeypatch):
    calls = []

    class MissingSentenceTransformer:
        def __init__(self, _model_name_or_path, **kwargs):
            calls.append(kwargs)
            raise OSError("model is absent")

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: SimpleNamespace(
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_cache_dir=None,
            embedding_allow_download=False,
        ),
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=MissingSentenceTransformer))

    with pytest.raises(embeddings.EmbeddingModelUnavailableError, match="not available in the local cache"):
        embeddings.EmbeddingService()._get_model()

    assert calls == [{"cache_folder": None, "local_files_only": True}]


def test_concurrent_first_calls_load_the_model_once(monkeypatch):
    # A warm-up and a question (or two questions after a restart) can both trigger the first
    # load; parallel SentenceTransformer construction is slow and can fail.
    import threading
    import time

    constructed = []

    class SlowSentenceTransformer(FakeEmbeddingModel):
        def __init__(self, _model_name_or_path, **_kwargs):
            constructed.append(threading.get_ident())
            time.sleep(0.2)

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: SimpleNamespace(
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_cache_dir=None,
            embedding_allow_download=False,
        ),
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=SlowSentenceTransformer))
    service = embeddings.EmbeddingService()

    async def both():
        return await asyncio.gather(service.embed_text("ısınma"), service.embed_text("soru"))

    assert asyncio.run(both()) == [[6.0], [4.0]]
    assert len(constructed) == 1
