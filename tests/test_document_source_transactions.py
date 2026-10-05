import io
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

# Route imports construct the async SQLAlchemy engine at import time.
# Keep this test isolated from the developer's local .env database.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from fastapi import UploadFile
from starlette.requests import Request

from app.api.routes import documents
from app.models.database import (
    Document,
    DocumentIndexEvent,
    DocumentVersion,
    IndexJob,
)
from app.services.document_source_events import SOURCE_STAGED


def request_for(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "headers": [],
        }
    )


class FakeQueue:
    def __init__(self):
        self.enqueued = []
        self.closed = False

    async def enqueue(self, job_id):
        self.enqueued.append(job_id)

    async def close(self):
        self.closed = True


class FakeStorage:
    def __init__(self):
        self.saved = []
        self.deleted = []

    async def save(self, data, suffix):
        path = f"/temporary/source{suffix}"
        self.saved.append((data, suffix, path))
        return path

    async def delete(self, path):
        self.deleted.append(path)


class FakeDb:
    def __init__(
        self,
        *,
        document=None,
        versions=(1,),
        duplicate=None,
    ):
        self.document = document
        self.versions = versions
        self.duplicate = duplicate
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed = []

    def add(self, item):
        self.added.append(item)

    def add_all(self, items):
        self.added.extend(items)

    async def flush(self):
        for item in self.added:
            if isinstance(item, Document) and item.id is None:
                item.id = 42

    async def scalar(self, _statement):
        return self.duplicate

    async def scalars(self, _statement):
        return self.versions

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1

    async def refresh(self, document):
        self.refreshed.append(document)
        if getattr(document, "created_at", None) is None:
            document.created_at = datetime.now(timezone.utc)
        if getattr(document, "updated_at", None) is None:
            document.updated_at = datetime.now(timezone.utc)


def event_from(db):
    events = [
        item
        for item in db.added
        if isinstance(item, DocumentIndexEvent)
    ]
    assert len(events) == 1
    return events[0]


@pytest.mark.asyncio
async def test_upload_commits_source_version_job_and_event_once(
    monkeypatch,
):
    db = FakeDb()
    storage = FakeStorage()
    queue = FakeQueue()

    kb = SimpleNamespace(id=4)
    workspace = SimpleNamespace(
        id=3,
        organization_id=2,
    )

    async def require_kb(
        _db,
        _user,
        _knowledge_base_id,
        _role,
    ):
        return kb, workspace, SimpleNamespace(role="manager")

    monkeypatch.setattr(
        documents,
        "require_knowledge_base_access",
        require_kb,
    )
    monkeypatch.setattr(
        documents,
        "RedisIndexQueue",
        lambda: queue,
    )
    monkeypatch.setattr(
        documents,
        "storage",
        storage,
    )
    monkeypatch.setattr(
        documents,
        "extract_text",
        lambda *_args: "hello",
    )
    monkeypatch.setattr(
        documents,
        "get_settings",
        lambda: SimpleNamespace(
            max_upload_bytes=1024,
        ),
    )
    monkeypatch.setattr(
        documents,
        "record_audit_event",
        lambda *_args, **_kwargs: None,
    )

    upload = UploadFile(
        file=io.BytesIO(b"hello"),
        filename="hello.txt",
    )

    result = await documents.upload(
        request_for("/documents/upload"),
        upload,
        4,
        {"sub": "1"},
        db,
    )

    assert result.id == 42
    assert result.source_revision == 1
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert storage.deleted == []

    versions = [
        item
        for item in db.added
        if isinstance(item, DocumentVersion)
    ]
    jobs = [
        item
        for item in db.added
        if isinstance(item, IndexJob)
    ]

    assert len(versions) == 1
    assert versions[0].version == 1
    assert len(jobs) == 1

    event = event_from(db)

    assert event.document_id == 42
    assert event.source_revision == 1
    assert event.operation == SOURCE_STAGED
    assert event.document_version == 1


@pytest.mark.asyncio
async def test_replace_locks_and_advances_source_revision_once(
    monkeypatch,
):
    document = SimpleNamespace(
        id=7,
        user_id=1,
        organization_id=2,
        workspace_id=3,
        knowledge_base_id=4,
        filename="old.txt",
        content_hash="old-hash",
        file_size=3,
        index_status="ready",
        index_error=None,
        active_version=1,
        source_revision=4,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db = FakeDb(
        document=document,
        versions=(1,),
    )
    storage = FakeStorage()
    queue = FakeQueue()
    locks = []

    async def require_doc(
        _db,
        _user,
        _document_id,
        _role,
    ):
        return document, SimpleNamespace(role="manager")

    async def lock_doc(_db, document_id):
        locks.append(document_id)
        return document

    monkeypatch.setattr(
        documents,
        "require_document_access",
        require_doc,
    )
    monkeypatch.setattr(
        documents,
        "lock_document_source",
        lock_doc,
    )
    monkeypatch.setattr(
        documents,
        "RedisIndexQueue",
        lambda: queue,
    )
    monkeypatch.setattr(
        documents,
        "storage",
        storage,
    )
    monkeypatch.setattr(
        documents,
        "extract_text",
        lambda *_args: "replacement",
    )
    monkeypatch.setattr(
        documents,
        "get_settings",
        lambda: SimpleNamespace(
            max_upload_bytes=1024,
        ),
    )
    monkeypatch.setattr(
        documents,
        "record_audit_event",
        lambda *_args, **_kwargs: None,
    )

    upload = UploadFile(
        file=io.BytesIO(b"replacement"),
        filename="new.txt",
    )

    result = await documents.replace_document(
        request_for("/documents/7/replace"),
        7,
        upload,
        {"sub": "1"},
        db,
    )

    assert result is document
    assert locks == [7]
    assert document.source_revision == 5
    assert document.active_version == 1
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert storage.deleted == []

    event = event_from(db)

    assert event.document_id == 7
    assert event.source_revision == 5
    assert event.operation == SOURCE_STAGED
    assert event.document_version == 2


@pytest.mark.asyncio
async def test_reindex_does_not_advance_source_revision_or_emit_source_event(
    monkeypatch,
):
    document = SimpleNamespace(
        id=7,
        user_id=1,
        organization_id=2,
        workspace_id=3,
        knowledge_base_id=4,
        filename="source.txt",
        content_hash="hash",
        file_size=3,
        index_status="ready",
        index_error=None,
        active_version=1,
        source_revision=9,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db = FakeDb(document=document)
    queue = FakeQueue()

    async def require_doc(
        _db,
        _user,
        _document_id,
        _role,
    ):
        return document, SimpleNamespace(role="manager")

    async def version_scalar(_statement):
        return SimpleNamespace(version=1)

    db.scalar = version_scalar

    monkeypatch.setattr(
        documents,
        "require_document_access",
        require_doc,
    )
    monkeypatch.setattr(
        documents,
        "RedisIndexQueue",
        lambda: queue,
    )
    monkeypatch.setattr(
        documents,
        "record_audit_event",
        lambda *_args, **_kwargs: None,
    )

    await documents.reindex_document(
        request_for("/documents/7/reindex"),
        7,
        {"sub": "1"},
        db,
    )

    assert document.source_revision == 9
    assert not any(
        isinstance(item, DocumentIndexEvent)
        for item in db.added
    )
