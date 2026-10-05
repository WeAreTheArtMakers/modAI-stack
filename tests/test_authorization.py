import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from qdrant_client import AsyncQdrantClient
from app.api.authorization import require_document_access, require_knowledge_base_access, require_workspace_access, resolve_knowledge_base_scope, role_allows
from app.models.database import Base, Document, KnowledgeBase, Membership, Organization, User, Workspace
from app.services.qdrant import QdrantService

@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        org_a, org_b = Organization(name="A", slug="a"), Organization(name="B", slug="b")
        wa, wb = Workspace(name="A", slug="a", organization=org_a), Workspace(name="B", slug="b", organization=org_b)
        ka, kb = KnowledgeBase(name="A", slug="a", workspace=wa), KnowledgeBase(name="B", slug="b", workspace=wb)
        ua, ub, uc = (User(email=f"{name}@example.com", password_hash="x") for name in "abc")
        db.add_all([org_a, org_b, wa, wb, ka, kb, ua, ub, uc]); await db.flush()
        db.add_all([Membership(user_id=ua.id, organization_id=org_a.id, workspace_id=wa.id, role="manager"), Membership(user_id=ub.id, organization_id=org_b.id, workspace_id=wb.id, role="admin"), Membership(user_id=uc.id, organization_id=org_a.id, workspace_id=wa.id, role="user")])
        doc = Document(user_id=ub.id, organization_id=org_b.id, workspace_id=wb.id, knowledge_base_id=kb.id, filename="b.txt", content="secret")
        doc_a = Document(user_id=ua.id, organization_id=org_a.id, workspace_id=wa.id, knowledge_base_id=ka.id, filename="a.txt", content="safe")
        db.add_all([doc, doc_a]); await db.commit()
        yield db, {"a": {"sub": str(ua.id)}, "b": {"sub": str(ub.id)}, "c": {"sub": str(uc.id)}, "ka": ka.id, "kb": kb.id, "doc": doc.id, "doc_a": doc_a.id, "owner_a": ua.id, "owner_b": ub.id, "employee": uc.id, "org_b": org_b.id, "workspace_b": wb.id}
    await engine.dispose()

@pytest.mark.asyncio
async def test_cross_organization_document_and_kb_access_is_denied(session):
    db, ids = session
    with pytest.raises(Exception): await require_document_access(db, ids["a"], ids["doc"])
    with pytest.raises(Exception): await require_knowledge_base_access(db, ids["a"], ids["kb"])

@pytest.mark.asyncio
async def test_authorized_manager_can_manage_own_document_and_kb(session):
    db, ids = session
    doc, membership = await require_document_access(db, ids["a"], ids["doc_a"])
    assert membership.role == "manager"

@pytest.mark.asyncio
async def test_workspace_and_multi_kb_scope_are_tenant_isolated(session):
    db, ids = session
    with pytest.raises(Exception):
        await require_workspace_access(db, ids["a"], 2)
    with pytest.raises(Exception):
        await resolve_knowledge_base_scope(db, ids["a"], [ids["kb"]])

    authorized_ids, scope = await resolve_knowledge_base_scope(db, ids["a"], [ids["ka"]])
    assert authorized_ids == [ids["ka"]]
    assert scope is not None and scope[1].id != 2

def test_role_policy_is_explicit():
    assert role_allows("admin", "manager")
    assert role_allows("manager", "user")
    assert not role_allows("user", "manager")

def test_qdrant_filter_is_tenant_scoped():
    qdrant = QdrantService()
    clauses = qdrant._user_filter(1, organization_id=2, workspace_id=3, knowledge_base_ids=[4, 5]).must
    assert any(getattr(c.match, "value", None) == 2 for c in clauses)
    assert any(getattr(c.match, "value", None) == 3 for c in clauses)


def test_retrieval_filter_uses_tenant_scope_and_active_version_not_uploader():
    clauses = QdrantService._retrieval_filter(2, 3, [4, 5]).must
    assert {condition.key for condition in clauses} == {
        "organization_id", "workspace_id", "knowledge_base_id", "is_active"
    }
    assert next(condition for condition in clauses if condition.key == "organization_id").match.value == 2
    assert next(condition for condition in clauses if condition.key == "workspace_id").match.value == 3
    assert list(next(condition for condition in clauses if condition.key == "knowledge_base_id").match.any) == [4, 5]
    assert next(condition for condition in clauses if condition.key == "is_active").match.value is True
    with pytest.raises(ValueError):
        QdrantService._retrieval_filter(2, 3, [])


@pytest.mark.asyncio
async def test_employee_retrieves_colleague_vector_but_not_foreign_or_inactive_vectors(session):
    db, ids = session
    authorized_ids, scope = await resolve_knowledge_base_scope(db, ids["c"], [ids["ka"]])
    assert scope is not None
    with pytest.raises(Exception):
        await resolve_knowledge_base_scope(db, ids["c"], [ids["kb"]])
    with pytest.raises(HTTPException) as empty_scope:
        await resolve_knowledge_base_scope(db, ids["c"], [])
    assert empty_scope.value.status_code == 400

    client = AsyncQdrantClient(":memory:")
    qdrant = QdrantService(client)
    try:
        await qdrant.upsert_document(
            user_id=ids["owner_a"], document_id=ids["doc_a"], filename="a.txt",
            organization_id=scope[1].organization_id, workspace_id=scope[1].id,
            knowledge_base_id=ids["ka"], chunks=["shared safe fact"], vectors=[[1.0, 0.0]],
        )
        await qdrant.upsert_document(
            user_id=ids["owner_a"], document_id=100, filename="inactive.txt",
            organization_id=scope[1].organization_id, workspace_id=scope[1].id,
            knowledge_base_id=ids["ka"], is_active=False,
            chunks=["obsolete fact"], vectors=[[1.0, 0.0]],
        )
        await qdrant.upsert_document(
            user_id=ids["owner_b"], document_id=ids["doc"], filename="b.txt",
            organization_id=ids["org_b"], workspace_id=ids["workspace_b"],
            knowledge_base_id=ids["kb"], chunks=["foreign secret"], vectors=[[1.0, 0.0]],
        )
        hits = await qdrant.search(
            vector=[1.0, 0.0], limit=10, organization_id=scope[1].organization_id,
            workspace_id=scope[1].id, knowledge_base_ids=authorized_ids,
        )
        assert [hit.payload["document_id"] for hit in hits] == [ids["doc_a"]]
        # Owner-scoped maintenance still cannot delete a colleague's vectors.
        await qdrant.delete_document_vectors(user_id=ids["employee"], document_id=ids["doc_a"])
        hits = await qdrant.search(
            vector=[1.0, 0.0], limit=10, organization_id=scope[1].organization_id,
            workspace_id=scope[1].id, knowledge_base_ids=authorized_ids,
        )
        assert [hit.payload["document_id"] for hit in hits] == [ids["doc_a"]]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_tombstoned_document_is_no_longer_accessible(session):
    from datetime import datetime, timezone

    db, ids = session

    document, _ = await require_document_access(
        db,
        ids["a"],
        ids["doc_a"],
    )

    document.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    with pytest.raises(HTTPException) as error:
        await require_document_access(
            db,
            ids["a"],
            ids["doc_a"],
        )

    assert error.value.status_code == 403
