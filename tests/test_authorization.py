import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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
        ua, ub = User(email="a@example.com", password_hash="x"), User(email="b@example.com", password_hash="x")
        db.add_all([org_a, org_b, wa, wb, ka, kb, ua, ub]); await db.flush()
        db.add_all([Membership(user_id=ua.id, organization_id=org_a.id, workspace_id=wa.id, role="manager"), Membership(user_id=ub.id, organization_id=org_b.id, workspace_id=wb.id, role="admin")])
        doc = Document(user_id=ub.id, organization_id=org_b.id, workspace_id=wb.id, knowledge_base_id=kb.id, filename="b.txt", content="secret")
        doc_a = Document(user_id=ua.id, organization_id=org_a.id, workspace_id=wa.id, knowledge_base_id=ka.id, filename="a.txt", content="safe")
        db.add_all([doc, doc_a]); await db.commit()
        yield db, {"a": {"sub": str(ua.id)}, "b": {"sub": str(ub.id)}, "ka": ka.id, "kb": kb.id, "doc": doc.id, "doc_a": doc_a.id}
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
