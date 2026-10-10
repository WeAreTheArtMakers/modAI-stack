"""Archiving an obsolete document: manager-only, idempotent, audited, and not a source change."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.routes import documents
from app.models.database import (
    AuditEvent,
    Base,
    Document,
    DocumentIndexEvent,
    KnowledgeBase,
    Membership,
    Organization,
    User,
    Workspace,
)
from app.models.schemas import DocumentListResponse, DocumentResponse


def request_for(path: str) -> Request:
    return Request({"type": "http", "method": "POST", "scheme": "http", "path": path, "headers": []})


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        organization = Organization(name="Org", slug="org")
        foreign_org = Organization(name="Foreign", slug="foreign")
        workspace = Workspace(name="Destek", slug="destek", organization=organization)
        foreign_ws = Workspace(name="Foreign", slug="foreign", organization=foreign_org)
        kb = KnowledgeBase(name="Destek", slug="destek", workspace=workspace)
        manager, employee, outsider = (User(email=f"{name}@example.com", password_hash="x") for name in ("manager", "employee", "outsider"))
        db.add_all([organization, foreign_org, workspace, foreign_ws, kb, manager, employee, outsider])
        await db.flush()
        db.add_all([
            Membership(user_id=manager.id, organization_id=organization.id, workspace_id=workspace.id, role="manager"),
            Membership(user_id=employee.id, organization_id=organization.id, workspace_id=workspace.id, role="user"),
            Membership(user_id=outsider.id, organization_id=foreign_org.id, workspace_id=foreign_ws.id, role="admin"),
        ])

        def document(filename):
            return Document(
                user_id=manager.id, organization_id=organization.id, workspace_id=workspace.id, knowledge_base_id=kb.id,
                filename=filename, content="", content_hash=filename * 4, active_version=1, source_revision=2,
            )

        old, current = document("destek-v2.md"), document("destek-v3.md")
        db.add_all([old, current])
        await db.flush()
        for doc in (old, current):
            db.add(DocumentIndexEvent(organization_id=organization.id, workspace_id=workspace.id, knowledge_base_id=kb.id,
                                      document_id=doc.id, source_revision=2, operation="active_version_published"))
        await db.commit()
        yield SimpleNamespace(
            db=db, kb_id=kb.id, org_id=organization.id, ws_id=workspace.id, manager_id=manager.id,
            manager={"sub": str(manager.id)}, employee={"sub": str(employee.id)}, outsider={"sub": str(outsider.id)},
            old_id=old.id, current_id=current.id,
        )
    await engine.dispose()


async def audit_actions(db):
    return list((await db.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())


async def source_event_count(db):
    return await db.scalar(select(func.count()).select_from(DocumentIndexEvent))


def test_archive_routes_are_registered_as_posts():
    routes = {(route.path, method) for route in documents.router.routes for method in route.methods}

    assert ("/documents/{document_id}/archive", "POST") in routes
    assert ("/documents/{document_id}/unarchive", "POST") in routes


@pytest.mark.asyncio
async def test_manager_archives_and_restores_without_a_source_change(env):
    events_before = await source_event_count(env.db)

    archived = await documents.archive_document(request_for(f"/documents/{env.old_id}/archive"), env.old_id, env.manager, env.db)

    response = DocumentResponse.model_validate(archived)
    assert response.archived_at is not None
    first_archived_at = response.archived_at
    assert archived.source_revision == 2 and archived.active_version == 1 and archived.deleted_at is None

    audits = await audit_actions(env.db)
    assert [(a.action, a.actor_user_id, a.resource_id, a.organization_id, a.workspace_id) for a in audits] == [
        ("document_archive", env.manager_id, str(env.old_id), env.org_id, env.ws_id),
    ]
    # Not a source change: no event, so an index generation keeps serving the same points.
    assert await source_event_count(env.db) == events_before

    # Idempotent: the first archive time is kept and nothing more is audited.
    again = await documents.archive_document(request_for(f"/documents/{env.old_id}/archive"), env.old_id, env.manager, env.db)
    assert DocumentResponse.model_validate(again).archived_at == first_archived_at
    assert len(await audit_actions(env.db)) == 1

    restored = await documents.unarchive_document(request_for(f"/documents/{env.old_id}/unarchive"), env.old_id, env.manager, env.db)
    assert DocumentResponse.model_validate(restored).archived_at is None
    assert restored.source_revision == 2

    restored_again = await documents.unarchive_document(request_for(f"/documents/{env.old_id}/unarchive"), env.old_id, env.manager, env.db)
    assert restored_again.archived_at is None

    audits = await audit_actions(env.db)
    assert [(a.action, a.actor_user_id) for a in audits] == [
        ("document_archive", env.manager_id),
        ("document_unarchive", env.manager_id),
    ]
    assert await source_event_count(env.db) == events_before

    # Unarchiving a document that was never archived changes nothing either.
    untouched = await documents.unarchive_document(request_for(f"/documents/{env.current_id}/unarchive"), env.current_id, env.manager, env.db)
    assert untouched.archived_at is None
    assert len(await audit_actions(env.db)) == 2


@pytest.mark.asyncio
async def test_only_managers_of_the_document_workspace_can_archive(env):
    for user in (env.employee, env.outsider):
        for action in (documents.archive_document, documents.unarchive_document):
            with pytest.raises(HTTPException) as error:
                await action(request_for(f"/documents/{env.old_id}/archive"), env.old_id, user, env.db)
            assert error.value.status_code == 403

    document = await env.db.get(Document, env.old_id)
    assert document.archived_at is None
    assert await audit_actions(env.db) == []


@pytest.mark.asyncio
async def test_deleted_documents_cannot_be_archived(env):
    document = await env.db.get(Document, env.old_id)
    document.deleted_at = datetime.now(timezone.utc)
    await env.db.commit()

    with pytest.raises(HTTPException) as error:
        await documents.archive_document(request_for(f"/documents/{env.old_id}/archive"), env.old_id, env.manager, env.db)

    assert error.value.status_code == 403
    assert (await env.db.get(Document, env.old_id)).archived_at is None


@pytest.mark.asyncio
async def test_list_keeps_archived_documents_with_their_archive_time(env):
    await documents.archive_document(request_for(f"/documents/{env.old_id}/archive"), env.old_id, env.manager, env.db)

    for user in (env.manager, env.employee):
        page = await documents.list_documents(knowledge_base_id=env.kb_id, limit=50, offset=0, user=user, db=env.db)
        items = {item.id: item for item in DocumentListResponse.model_validate(page).items}

        assert page.total == 2
        assert items[env.old_id].archived_at is not None
        assert items[env.current_id].archived_at is None


@pytest.mark.asyncio
async def test_archive_refuses_a_document_deleted_while_waiting_for_its_lock(monkeypatch):
    document = SimpleNamespace(id=7, organization_id=2, workspace_id=3, knowledge_base_id=4, archived_at=None, deleted_at=None)
    locked = SimpleNamespace(**{**vars(document), "deleted_at": datetime.now(timezone.utc)})

    class Db:
        rollbacks = 0
        commits = 0

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    async def require_doc(_db, _user, _document_id, role):
        assert role == "manager"
        return document, SimpleNamespace(role="manager")

    async def lock_doc(_db, document_id):
        assert document_id == 7
        return locked

    def no_audit(*_args, **_kwargs):
        raise AssertionError("a refused archive must not be audited")

    monkeypatch.setattr(documents, "require_document_access", require_doc)
    monkeypatch.setattr(documents, "lock_document_source", lock_doc)
    monkeypatch.setattr(documents, "record_audit_event", no_audit)
    db = Db()

    with pytest.raises(HTTPException) as error:
        await documents.archive_document(request_for("/documents/7/archive"), 7, {"sub": "1"}, db)

    assert error.value.status_code == 409
    assert locked.archived_at is None
    assert db.rollbacks == 1 and db.commits == 0


@pytest.mark.asyncio
async def test_archive_commit_failure_rolls_back_and_reports_unavailable(monkeypatch):
    document = SimpleNamespace(id=7, organization_id=2, workspace_id=3, knowledge_base_id=4, archived_at=None, deleted_at=None)

    class FailingDb:
        rollbacks = 0

        def add(self, _item):
            pass

        async def commit(self):
            raise RuntimeError("forced commit failure")

        async def rollback(self):
            self.rollbacks += 1

    async def require_doc(_db, _user, _document_id, _role):
        return document, SimpleNamespace(role="manager")

    async def lock_doc(_db, _document_id):
        return document

    monkeypatch.setattr(documents, "require_document_access", require_doc)
    monkeypatch.setattr(documents, "lock_document_source", lock_doc)
    db = FailingDb()

    with pytest.raises(HTTPException) as error:
        await documents.archive_document(request_for("/documents/7/archive"), 7, {"sub": "1"}, db)

    assert error.value.status_code == 503
    assert db.rollbacks == 1
