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
from app import worker


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


@pytest.mark.asyncio
async def test_worker_releases_its_document_version_lock_after_indexing(monkeypatch):
    job = SimpleNamespace(id="job-7", document_id=7, version=1, status="queued", attempts=0, error=None)
    version = SimpleNamespace(version=1, stored_path="/temporary/source.txt", content_hash="hash", file_size=5, status="queued")
    document = SimpleNamespace(
        id=7,
        user_id=1,
        organization_id=2,
        workspace_id=3,
        knowledge_base_id=4,
        filename="source.txt",
        active_version=1,
        content="",
        content_hash="old",
        file_size=0,
        index_status="queued",
        index_error=None,
    )

    class Db:
        async def get(self, model, _identifier):
            return job if model is worker.IndexJob else document

        async def scalar(self, _statement):
            return version

        async def commit(self):
            pass

    class SessionContext:
        async def __aenter__(self):
            return Db()

        async def __aexit__(self, *_args):
            pass

    class Redis:
        def __init__(self):
            self.values = {}

        async def set(self, key, value, nx, ex):
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

        async def eval(self, script, _key_count, key, value):
            if self.values.get(key) == value:
                del self.values[key]
                return 1
            return 0

    class Queue:
        def __init__(self):
            self.client = Redis()
            self.events = []

        async def publish_progress(self, event, _workspace_id):
            self.events.append(event)

        async def close(self):
            pass

    queue = Queue()

    async def read(_path):
        return b"indexed"

    async def embed_texts(_chunks):
        return [[0.1, 0.2]]

    async def upsert_document(**_kwargs):
        pass

    monkeypatch.setattr(worker, "SessionLocal", SessionContext)
    monkeypatch.setattr(worker, "RedisIndexQueue", lambda: queue)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(indexing_job_timeout_seconds=60, chunk_size=10, chunk_overlap=1))
    monkeypatch.setattr(worker, "storage", SimpleNamespace(read=read))
    monkeypatch.setattr(worker, "extract_text", lambda *_args: "indexed")
    monkeypatch.setattr(worker, "chunk_text", lambda *_args: ["indexed"])
    monkeypatch.setattr(worker, "get_embedding_service", lambda: SimpleNamespace(embed_texts=embed_texts))
    monkeypatch.setattr(worker, "qdrant_service", SimpleNamespace(upsert_document=upsert_document))
    monkeypatch.setattr(worker, "metrics", SimpleNamespace(event=lambda *_args: None))

    await worker.process_job(job.id)

    assert job.status == "ready"
    assert queue.client.values == {}
