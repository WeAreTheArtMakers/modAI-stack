import io
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from starlette.requests import Request

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.routes import documents
from app.models.schemas import DocumentResponse


def request_for(path: str) -> Request:
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": path, "headers": []})


class DeferredUpdatedDocument:
    """Raises while serializing until the database refreshes server-managed fields."""

    def __init__(self):
        self.id = 7
        self.user_id = 1
        self.organization_id = 2
        self.workspace_id = 3
        self.knowledge_base_id = 4
        self.filename = "original.txt"
        self.content_hash = "old-hash"
        self.file_size = 5
        self.index_status = "ready"
        self.index_error = None
        self.active_version = 1
        self.created_at = datetime.now(timezone.utc)
        self.refreshed = False

    @property
    def updated_at(self):
        if not self.refreshed:
            raise RuntimeError("server-managed updated_at was not refreshed")
        return datetime.now(timezone.utc)


class FakeDb:
    def __init__(self, document, versions=(1,)):
        self.document = document
        self.versions = versions
        self.refreshed = []
        self.added = []

    async def scalar(self, _statement):
        return SimpleNamespace(version=self.document.active_version)

    async def scalars(self, _statement):
        return self.versions

    def add(self, item):
        self.added.append(item)

    def add_all(self, items):
        self.added.extend(items)

    async def commit(self):
        pass

    async def refresh(self, document):
        document.refreshed = True
        self.refreshed.append(document)


class FakeQueue:
    async def enqueue(self, _job_id):
        pass

    async def close(self):
        pass


async def document_access(_db, _user, _document_id, _required_role="user"):
    return _db.document, SimpleNamespace(role="manager")


def install_route_fakes(monkeypatch):
    monkeypatch.setattr(documents, "require_document_access", document_access)
    monkeypatch.setattr(documents, "RedisIndexQueue", FakeQueue)
    monkeypatch.setattr(documents, "record_audit_event", lambda *_args, **_kwargs: None)


@pytest.mark.asyncio
async def test_reindex_refreshes_server_managed_fields_before_document_response(monkeypatch):
    install_route_fakes(monkeypatch)
    document = DeferredUpdatedDocument()
    db = FakeDb(document)

    result = await documents.reindex_document(request_for("/documents/7/reindex"), 7, {"sub": "1"}, db)

    assert db.refreshed == [document]
    assert DocumentResponse.model_validate(result).updated_at is not None


@pytest.mark.asyncio
async def test_replace_refreshes_server_managed_fields_before_document_response(monkeypatch):
    install_route_fakes(monkeypatch)
    document = DeferredUpdatedDocument()
    db = FakeDb(document)

    async def save(_data, _suffix):
        return "/temporary/updated.txt"

    monkeypatch.setattr(documents, "extract_text", lambda *_args: "updated text")
    monkeypatch.setattr(documents, "storage", SimpleNamespace(save=save))
    monkeypatch.setattr(documents, "get_settings", lambda: SimpleNamespace(max_upload_bytes=1024))
    upload = UploadFile(file=io.BytesIO(b"updated text"), filename="updated.txt")

    result = await documents.replace_document(request_for("/documents/7/replace"), 7, upload, {"sub": "1"}, db)

    assert db.refreshed == [document]
    assert DocumentResponse.model_validate(result).updated_at is not None
