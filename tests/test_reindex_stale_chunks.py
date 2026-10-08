import os
from types import SimpleNamespace

import pytest

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app import worker
from app.models.database import Document, IndexJob
from app.services.qdrant import QdrantService


class RecordingClient(AsyncQdrantClient):
    """In-process Qdrant that records delete selectors for scope assertions."""

    def __init__(self):
        super().__init__(location=":memory:")
        self.deletes = []

    async def delete(self, *args, **kwargs):
        self.deletes.append(kwargs)
        return await super().delete(*args, **kwargs)


def make_service():
    return QdrantService(client=RecordingClient())


def vectors(count):
    return [[1.0, float(index + 1), 0.0, 0.0] for index in range(count)]


async def upsert(
    service,
    count,
    *,
    user_id=1,
    organization_id=2,
    document_id=7,
    document_version=3,
    is_active=True,
):
    await service.upsert_document(
        user_id=user_id,
        document_id=document_id,
        filename="source.txt",
        organization_id=organization_id,
        workspace_id=3,
        knowledge_base_id=4,
        document_version=document_version,
        is_active=is_active,
        chunks=[f"chunk {index}" for index in range(count)],
        vectors=vectors(count),
    )


async def stored_points(service, *, document_id=7, document_version=3):
    points, _ = await service.client.scroll(
        collection_name=service.collection_name,
        scroll_filter=models.Filter(must=[
            models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
            models.FieldCondition(key="document_version", match=models.MatchValue(value=document_version)),
        ]),
        limit=1000,
        with_payload=True,
    )
    return sorted(points, key=lambda point: point.payload["chunk_index"])


async def stored_chunk_indexes(service, **scope):
    return [point.payload["chunk_index"] for point in await stored_points(service, **scope)]


@pytest.mark.asyncio
@pytest.mark.parametrize(("old_count", "new_count"), [(10, 7), (7, 7), (7, 10)])
async def test_same_version_reindex_leaves_exactly_current_chunks(old_count, new_count):
    service = make_service()

    await upsert(service, old_count)
    await upsert(service, new_count)

    assert await stored_chunk_indexes(service) == list(range(new_count))
    texts = [point.payload["text"] for point in await stored_points(service)]
    assert texts == [f"chunk {index}" for index in range(new_count)]


@pytest.mark.asyncio
async def test_repeated_reindex_is_idempotent():
    service = make_service()
    await upsert(service, 10)
    await upsert(service, 7)
    first_ids = [point.id for point in await stored_points(service)]

    await upsert(service, 7)
    await upsert(service, 7)

    assert [point.id for point in await stored_points(service)] == first_ids
    assert await stored_chunk_indexes(service) == list(range(7))


@pytest.mark.asyncio
async def test_reindex_does_not_touch_other_documents_versions_or_tenants():
    service = make_service()
    await upsert(service, 10)
    await upsert(service, 10, document_id=8)
    await upsert(service, 10, document_version=2, is_active=False)
    await upsert(service, 10, user_id=5, organization_id=6, document_id=9)

    await upsert(service, 7)

    assert await stored_chunk_indexes(service) == list(range(7))
    assert await stored_chunk_indexes(service, document_id=8) == list(range(10))
    assert await stored_chunk_indexes(service, document_version=2) == list(range(10))
    assert await stored_chunk_indexes(service, document_id=9) == list(range(10))


@pytest.mark.asyncio
async def test_stale_chunk_removal_is_scoped_to_owner_document_and_version():
    service = make_service()
    await upsert(service, 10)
    service.client.deletes.clear()

    await upsert(service, 7)

    assert len(service.client.deletes) == 1
    call = service.client.deletes[0]
    assert call["collection_name"] == "rag_documents"
    assert call["wait"] is True
    conditions = {
        condition.key: condition
        for condition in call["points_selector"].filter.must
    }
    assert conditions["user_id"].match.value == 1
    assert conditions["document_id"].match.value == 7
    assert conditions["document_version"].match.value == 3
    assert conditions["chunk_index"].range == models.Range(gte=7)
    assert "is_active" not in conditions


@pytest.mark.asyncio
async def test_reindex_to_zero_chunks_removes_that_version_only():
    service = make_service()
    await upsert(service, 10)
    await upsert(service, 10, document_version=2, is_active=False)

    await upsert(service, 0)

    assert await stored_chunk_indexes(service) == []
    assert await stored_chunk_indexes(service, document_version=2) == list(range(10))


@pytest.mark.asyncio
async def test_zero_chunks_without_collection_is_a_noop():
    service = make_service()

    await upsert(service, 0)

    collections = await service.client.get_collections()
    assert collections.collections == []
    assert service.client.deletes == []


@pytest.mark.asyncio
async def test_authorized_search_never_returns_removed_trailing_chunks():
    service = make_service()
    await upsert(service, 10)
    await upsert(service, 7)

    hits = await service.search(
        vector=[1.0, 10.0, 0.0, 0.0],
        limit=10,
        organization_id=2,
        workspace_id=3,
        knowledge_base_ids=[4],
    )

    assert sorted(hit.payload["chunk_index"] for hit in hits) == list(range(7))


# Worker-level coverage with the real QdrantService and an in-process client.


class Redis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, nx, ex):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, _script, _count, key, value):
        if self.values.get(key) == value:
            del self.values[key]
            return 1
        return 0


class Queue:
    def __init__(self):
        self.client = Redis()

    async def publish_progress(self, _event, _workspace_id):
        pass

    async def close(self):
        pass


class Db:
    def __init__(self, job, version, document):
        self.job = job
        self.version = version
        self.document = document

    async def get(self, model, _identifier):
        if model is IndexJob:
            return self.job
        if model is Document:
            return self.document
        raise AssertionError(model)

    async def scalar(self, _statement):
        return self.version

    def add(self, _item):
        pass

    async def commit(self):
        pass


class SessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        pass


def make_document(active_version):
    return SimpleNamespace(
        id=7,
        user_id=1,
        organization_id=2,
        workspace_id=3,
        knowledge_base_id=4,
        filename="source.txt",
        active_version=active_version,
        source_revision=1,
        deleted_at=None,
        content="old",
        content_hash="old-hash",
        file_size=3,
        index_status="queued",
        index_error=None,
    )


async def run_job(monkeypatch, service, *, document, version, status, chunk_count):
    job = SimpleNamespace(
        id=f"job-{version}-{status}-{chunk_count}",
        document_id=7,
        version=version,
        status="queued",
        attempts=0,
        error=None,
    )
    version_record = SimpleNamespace(
        version=version,
        stored_path="/temporary/source.txt",
        content_hash=f"hash-{version}",
        file_size=10 + version,
        status=status,
    )
    db = Db(job, version_record, document)

    async def read(_path):
        return b"source"

    async def lock_document(_db, _document_id):
        return document

    async def embed_texts(chunks):
        return vectors(len(chunks))

    monkeypatch.setattr(worker, "SessionLocal", lambda: SessionContext(db))
    monkeypatch.setattr(worker, "RedisIndexQueue", Queue)
    monkeypatch.setattr(worker, "lock_document_source", lock_document)
    monkeypatch.setattr(worker, "storage", SimpleNamespace(read=read))
    monkeypatch.setattr(worker, "extract_text", lambda *_args: "source")
    monkeypatch.setattr(
        worker,
        "chunk_text",
        lambda *_args: [f"chunk {index}" for index in range(chunk_count)],
    )
    monkeypatch.setattr(
        worker,
        "get_embedding_service",
        lambda: SimpleNamespace(embed_texts=embed_texts),
    )
    monkeypatch.setattr(worker, "qdrant_service", service)
    monkeypatch.setattr(worker, "metrics", SimpleNamespace(event=lambda *_args: None))
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            indexing_job_timeout_seconds=60,
            indexing_max_retries=3,
            chunk_size=10,
            chunk_overlap=1,
        ),
    )

    await worker.process_job(job.id)
    assert job.status == "ready"


async def active_flags(service, *, document_version):
    return {
        point.payload["chunk_index"]: point.payload["is_active"]
        for point in await stored_points(service, document_version=document_version)
    }


@pytest.mark.asyncio
async def test_worker_active_reindex_with_fewer_chunks_leaves_no_stale_chunks(monkeypatch):
    service = make_service()
    document = make_document(active_version=3)

    await run_job(monkeypatch, service, document=document, version=3, status="queued", chunk_count=10)
    await run_job(monkeypatch, service, document=document, version=3, status="ready", chunk_count=7)

    assert await active_flags(service, document_version=3) == {index: True for index in range(7)}
    assert document.active_version == 3


@pytest.mark.asyncio
async def test_worker_replacement_publication_still_swaps_versions(monkeypatch):
    service = make_service()
    document = make_document(active_version=3)
    await run_job(monkeypatch, service, document=document, version=3, status="queued", chunk_count=10)

    await run_job(monkeypatch, service, document=document, version=4, status="queued", chunk_count=7)

    assert document.active_version == 4
    assert await active_flags(service, document_version=4) == {index: True for index in range(7)}
    assert await stored_chunk_indexes(service, document_version=3) == []


@pytest.mark.asyncio
async def test_worker_stale_version_stays_inactive_and_leaves_active_version_intact(monkeypatch):
    service = make_service()
    document = make_document(active_version=3)
    await run_job(monkeypatch, service, document=document, version=3, status="queued", chunk_count=10)

    await run_job(monkeypatch, service, document=document, version=2, status="queued", chunk_count=5)

    assert document.active_version == 3
    assert await active_flags(service, document_version=2) == {index: False for index in range(5)}
    assert await active_flags(service, document_version=3) == {index: True for index in range(10)}
