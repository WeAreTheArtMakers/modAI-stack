import os
from types import SimpleNamespace

import pytest

os.environ["DATABASE_URL"] = (
    "sqlite+aiosqlite:///:memory:"
)

from app import worker
from app.models.database import (
    Document,
    DocumentIndexEvent,
    DocumentVersion,
    IndexJob,
    WorkspaceRetrievalAssignment,
)
from app.services.document_source_events import (
    ACTIVE_VERSION_PUBLISHED,
)


class Redis:
    def __init__(self):
        self.values = {}

    async def set(
        self,
        key,
        value,
        nx,
        ex,
    ):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(
        self,
        _script,
        _count,
        key,
        value,
    ):
        if self.values.get(key) == value:
            del self.values[key]
            return 1
        return 0


class Queue:
    def __init__(self):
        self.client = Redis()
        self.events = []
        self.enqueued = []

    async def publish_progress(
        self,
        event,
        _workspace_id,
    ):
        self.events.append(event)

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)

    async def close(self):
        pass


class Qdrant:
    def __init__(self):
        self.upserts = []
        self.activations = []
        self.deletions = []

    async def upsert_document(
        self,
        **kwargs,
    ):
        self.upserts.append(kwargs)

    async def set_version_active(
        self,
        **kwargs,
    ):
        self.activations.append(kwargs)

    async def delete_document_vectors(
        self,
        **kwargs,
    ):
        self.deletions.append(kwargs)


class Db:
    def __init__(
        self,
        job,
        version,
        document,
    ):
        self.job = job
        self.version = version
        self.document = document
        self.added = []
        self.commits = 0

    async def get(
        self,
        model,
        _identifier,
    ):
        if model is IndexJob:
            return self.job
        if model is Document:
            return self.document
        if model is WorkspaceRetrievalAssignment:
            return None  # legacy serving: no index generation to mirror into
        raise AssertionError(model)

    async def scalar(
        self,
        _statement,
    ):
        return self.version

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


class SessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(
        self,
        *_args,
    ):
        pass


def make_document(
    *,
    active_version,
    source_revision,
    index_status="queued",
):
    return SimpleNamespace(
        id=7,
        user_id=1,
        organization_id=2,
        workspace_id=3,
        knowledge_base_id=4,
        filename="source.txt",
        active_version=active_version,
        source_revision=source_revision,
        deleted_at=None,
        content="old",
        content_hash="old-hash",
        file_size=3,
        index_status=index_status,
        index_error=None,
    )


def make_job(version):
    return SimpleNamespace(
        id=f"job-{version}",
        document_id=7,
        version=version,
        status="queued",
        attempts=0,
        error=None,
    )


def make_version(
    version,
    *,
    status="queued",
):
    return SimpleNamespace(
        version=version,
        stored_path="/temporary/source.txt",
        content_hash=f"hash-{version}",
        file_size=10 + version,
        status=status,
    )


async def run_worker(
    monkeypatch,
    *,
    job,
    version,
    document,
):
    db = Db(
        job,
        version,
        document,
    )
    queue = Queue()
    qdrant = Qdrant()

    monkeypatch.setattr(
        worker,
        "SessionLocal",
        lambda: SessionContext(db),
    )
    monkeypatch.setattr(
        worker,
        "RedisIndexQueue",
        lambda: queue,
    )

    async def lock_document(
        _db,
        _document_id,
    ):
        return document

    monkeypatch.setattr(
        worker,
        "lock_document_source",
        lock_document,
    )

    async def read(_path):
        return b"indexed"

    monkeypatch.setattr(
        worker,
        "storage",
        SimpleNamespace(read=read),
    )

    monkeypatch.setattr(
        worker,
        "extract_text",
        lambda *_args: "indexed",
    )

    monkeypatch.setattr(
        worker,
        "chunk_text",
        lambda *_args: ["indexed"],
    )

    async def embed_texts(_chunks):
        return [[0.1, 0.2]]

    monkeypatch.setattr(
        worker,
        "get_embedding_service",
        lambda: SimpleNamespace(
            embed_texts=embed_texts,
        ),
    )

    monkeypatch.setattr(
        worker,
        "qdrant_service",
        qdrant,
    )

    monkeypatch.setattr(
        worker,
        "metrics",
        SimpleNamespace(
            event=lambda *_args: None,
        ),
    )

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

    return db, queue, qdrant


def source_events(db):
    return [
        item
        for item in db.added
        if isinstance(
            item,
            DocumentIndexEvent,
        )
    ]


@pytest.mark.asyncio
async def test_initial_publication_emits_event_and_advances_revision(
    monkeypatch,
):
    document = make_document(
        active_version=1,
        source_revision=1,
    )
    job = make_job(1)
    version = make_version(1)

    db, _queue, qdrant = await run_worker(
        monkeypatch,
        job=job,
        version=version,
        document=document,
    )

    assert document.active_version == 1
    assert document.source_revision == 2
    assert document.content_hash == "hash-1"

    events = source_events(db)

    assert len(events) == 1
    assert (
        events[0].operation
        == ACTIVE_VERSION_PUBLISHED
    )
    assert events[0].source_revision == 2
    assert events[0].document_version == 1

    assert len(qdrant.upserts) == 1
    assert (
        qdrant.upserts[0]["is_active"]
        is True
    )

    assert qdrant.activations == []
    assert qdrant.deletions == []

    assert version.status == "ready"
    assert job.status == "ready"


@pytest.mark.asyncio
async def test_stale_older_version_cannot_move_active_version_backwards(
    monkeypatch,
):
    document = make_document(
        active_version=3,
        source_revision=7,
        index_status="ready",
    )
    original_hash = document.content_hash

    job = make_job(2)
    version = make_version(2)

    db, _queue, qdrant = await run_worker(
        monkeypatch,
        job=job,
        version=version,
        document=document,
    )

    assert document.active_version == 3
    assert document.source_revision == 7
    assert document.content_hash == original_hash

    assert source_events(db) == []

    assert len(qdrant.upserts) == 1
    assert (
        qdrant.upserts[0]["is_active"]
        is False
    )

    assert qdrant.activations == []
    assert qdrant.deletions == []

    assert version.status == "ready"
    assert job.status == "ready"


@pytest.mark.asyncio
async def test_active_reindex_does_not_create_source_revision(
    monkeypatch,
):
    document = make_document(
        active_version=3,
        source_revision=7,
        index_status="queued",
    )

    job = make_job(3)
    version = make_version(
        3,
        status="ready",
    )

    db, _queue, qdrant = await run_worker(
        monkeypatch,
        job=job,
        version=version,
        document=document,
    )

    assert document.active_version == 3
    assert document.source_revision == 7
    assert source_events(db) == []

    assert len(qdrant.upserts) == 1
    assert (
        qdrant.upserts[0]["is_active"]
        is True
    )

    assert job.status == "ready"


@pytest.mark.asyncio
async def test_newer_replacement_publishes_and_deactivates_old_version(
    monkeypatch,
):
    document = make_document(
        active_version=1,
        source_revision=4,
    )

    job = make_job(3)
    version = make_version(3)

    db, _queue, qdrant = await run_worker(
        monkeypatch,
        job=job,
        version=version,
        document=document,
    )

    assert document.active_version == 3
    assert document.source_revision == 5
    assert document.content_hash == "hash-3"

    events = source_events(db)

    assert len(events) == 1
    assert events[0].source_revision == 5
    assert events[0].document_version == 3

    assert len(qdrant.upserts) == 1
    assert (
        qdrant.upserts[0]["is_active"]
        is False
    )

    assert qdrant.activations == [
        {
            "user_id": 1,
            "document_id": 7,
            "document_version": 3,
            "active": True,
        },
        {
            "user_id": 1,
            "document_id": 7,
            "document_version": 1,
            "active": False,
        },
    ]

    assert qdrant.deletions == [
        {
            "user_id": 1,
            "document_id": 7,
            "document_version": 1,
        }
    ]


@pytest.mark.asyncio
async def test_tombstoned_document_job_never_publishes_vectors(
    monkeypatch,
):
    from datetime import datetime, timezone

    document = make_document(
        active_version=2,
        source_revision=5,
        index_status="deleted",
    )
    document.deleted_at = datetime.now(timezone.utc)

    job = make_job(2)
    version = make_version(2)

    db, _queue, qdrant = await run_worker(
        monkeypatch,
        job=job,
        version=version,
        document=document,
    )

    assert job.status == "cancelled"
    assert job.error is None
    assert document.source_revision == 5

    assert source_events(db) == []
    assert qdrant.upserts == []
    assert qdrant.activations == []
    assert qdrant.deletions == []


@pytest.mark.asyncio
async def test_publication_is_mirrored_with_the_revision_it_publishes(
    monkeypatch,
):
    calls = []

    async def mirror(_db, *, document, version, text, source_revision):
        # Called before the publication changes any source state.
        calls.append((source_revision, document.source_revision, version.status, version.version, text))
        return True

    monkeypatch.setattr(worker, "mirror_to_active_generation", mirror)

    document = make_document(active_version=1, source_revision=1)
    job = make_job(1)
    await run_worker(monkeypatch, job=job, version=make_version(1), document=document)
    assert calls == [(2, 1, "queued", 1, "indexed")] and job.status == "ready"

    # An older version finishing late is not the active source: never mirrored.
    calls.clear()
    stale = make_document(active_version=3, source_revision=7, index_status="ready")
    await run_worker(monkeypatch, job=make_job(2), version=make_version(2), document=stale)
    assert calls == []


@pytest.mark.asyncio
async def test_a_failed_mirror_does_not_publish_the_source(
    monkeypatch,
):
    async def mirror(*_args, **_kwargs):
        raise RuntimeError("generation unavailable")

    monkeypatch.setattr(worker, "mirror_to_active_generation", mirror)

    job = make_job(1)
    version = make_version(1)
    document = make_document(active_version=1, source_revision=1)
    db, queue, _qdrant = await run_worker(
        monkeypatch,
        job=job,
        version=version,
        document=document,
    )

    # Nothing was published: same revision, no event, version not ready; the job is retried.
    assert job.status == "queued" and queue.enqueued == [job.id]
    assert document.source_revision == 1 and version.status == "queued"
    assert source_events(db) == []


@pytest.mark.asyncio
async def test_worker_preloads_active_generation_models_before_taking_jobs(monkeypatch):
    order = []

    class Stop(Exception):
        pass

    class StartQueue:
        async def dequeue(self, timeout):
            order.append("dequeue")
            raise Stop

        async def close(self):
            pass

    async def warm(_db):
        order.append("warm")
        raise RuntimeError("model missing")  # never keeps the worker from starting

    monkeypatch.setattr(worker, "SessionLocal", lambda: SessionContext(object()))
    monkeypatch.setattr(worker, "warm_active_generation_models", warm)
    monkeypatch.setattr(worker, "RedisIndexQueue", StartQueue)
    with pytest.raises(Stop):
        await worker.worker_main()
    assert order == ["warm", "dequeue"]
