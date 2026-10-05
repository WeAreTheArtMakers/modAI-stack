import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.routes import documents
from app.models.database import DocumentIndexEvent
from app.services.document_source_events import DOCUMENT_DELETED


def request_for(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "DELETE",
            "scheme": "http",
            "path": path,
            "headers": [],
        }
    )


class Result:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeDb:
    def __init__(self, jobs):
        self.jobs = jobs
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def scalars(self, _statement):
        return Result(self.jobs)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_delete_creates_durable_tombstone_without_physical_cleanup(
    monkeypatch,
):
    document = SimpleNamespace(
        id=7,
        user_id=1,
        organization_id=2,
        workspace_id=3,
        knowledge_base_id=4,
        filename="source.txt",
        active_version=2,
        source_revision=4,
        deleted_at=None,
        content_hash="active-hash",
        index_status="ready",
        index_error=None,
    )

    queued = SimpleNamespace(
        status="queued",
        error="old",
    )
    processing = SimpleNamespace(
        status="processing",
        error="old",
    )
    db = FakeDb(
        [queued, processing]
    )

    async def require_doc(
        _db,
        _user,
        _document_id,
        _role,
    ):
        return document, SimpleNamespace(role="manager")

    async def lock_doc(_db, document_id):
        assert document_id == 7
        return document

    async def forbidden_qdrant_delete(**_kwargs):
        raise AssertionError(
            "physical Qdrant cleanup must not happen in tombstone transaction"
        )

    async def forbidden_storage_delete(_path):
        raise AssertionError(
            "physical file cleanup must not happen in tombstone transaction"
        )

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
        "record_audit_event",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        documents,
        "qdrant_service",
        SimpleNamespace(
            delete_document_vectors=forbidden_qdrant_delete
        ),
    )
    monkeypatch.setattr(
        documents,
        "storage",
        SimpleNamespace(
            delete=forbidden_storage_delete
        ),
    )

    result = await documents.delete_document(
        request_for("/documents/7"),
        7,
        {"sub": "1"},
        db,
    )

    assert result is None
    assert document.deleted_at is not None
    assert document.deleted_at.tzinfo is not None
    assert document.source_revision == 5
    assert document.index_status == "deleted"
    assert document.active_version == 2

    assert queued.status == "cancelled"
    assert queued.error is None
    assert processing.status == "cancelled"
    assert processing.error is None
    assert db.commits == 1
    assert db.rollbacks == 0

    events = [
        item
        for item in db.added
        if isinstance(item, DocumentIndexEvent)
    ]

    assert len(events) == 1
    event = events[0]

    assert event.document_id == 7
    assert event.source_revision == 5
    assert event.operation == DOCUMENT_DELETED
    assert event.document_version == 2
    assert event.content_hash == "active-hash"


@pytest.mark.asyncio
async def test_delete_rollback_does_not_touch_expired_document_state(
    monkeypatch,
):
    class ExpiringDocument:
        def __init__(self):
            self._expired = False
            self._id = 7
            self.user_id = 1
            self.organization_id = 2
            self.workspace_id = 3
            self.knowledge_base_id = 4
            self.active_version = 1
            self.source_revision = 4
            self.deleted_at = None
            self.content_hash = "hash"
            self.index_status = "ready"
            self.index_error = None

        @property
        def id(self):
            if self._expired:
                raise RuntimeError(
                    "expired ORM state accessed after rollback"
                )
            return self._id

    document = ExpiringDocument()

    class Result:
        def all(self):
            return []

    class FailingDb:
        def __init__(self):
            self.added = []
            self.rollback_count = 0

        async def scalars(self, _statement):
            return Result()

        def add(self, item):
            self.added.append(item)

        async def commit(self):
            raise RuntimeError("forced commit failure")

        async def rollback(self):
            self.rollback_count += 1
            document._expired = True

    db = FailingDb()

    async def require_doc(
        _db,
        _user,
        _document_id,
        _role,
    ):
        return document, SimpleNamespace(role="manager")

    async def lock_doc(_db, document_id):
        assert document_id == 7
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
        "record_audit_event",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(HTTPException) as error:
        await documents.delete_document(
            request_for("/documents/7"),
            7,
            {"sub": "1"},
            db,
        )

    assert error.value.status_code == 503
    assert db.rollback_count == 1
