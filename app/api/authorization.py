from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import Document, KnowledgeBase, Membership, Workspace

ROLE_ORDER = {"user": 1, "manager": 2, "admin": 3}
def role_allows(role: str, minimum: str) -> bool: return ROLE_ORDER.get(role, 0) >= ROLE_ORDER[minimum]

async def require_organization_access(db: AsyncSession, user: dict, organization_id: int, minimum_role: str = "user") -> Membership:
    membership = await db.scalar(select(Membership).where(Membership.user_id == int(user["sub"]), Membership.organization_id == organization_id, Membership.workspace_id.is_(None)))
    if not membership:
        membership = await db.scalar(select(Membership).where(Membership.user_id == int(user["sub"]), Membership.organization_id == organization_id))
    if not membership or not role_allows(membership.role, minimum_role): raise HTTPException(403, "Organization access denied")
    return membership

async def require_workspace_access(db: AsyncSession, user: dict, workspace_id: int, minimum_role: str = "user") -> Membership:
    membership = await db.scalar(select(Membership).where(Membership.user_id == int(user["sub"]), Membership.workspace_id == workspace_id))
    if not membership or not role_allows(membership.role, minimum_role): raise HTTPException(403, "Workspace access denied")
    return membership

async def require_knowledge_base_access(db: AsyncSession, user: dict, knowledge_base_id: int, minimum_role: str = "user") -> tuple[KnowledgeBase, Workspace, Membership]:
    row = (await db.execute(select(KnowledgeBase, Workspace, Membership).join(Workspace).join(Membership, Membership.workspace_id == Workspace.id).where(KnowledgeBase.id == knowledge_base_id, Membership.user_id == int(user["sub"])))).first()
    if not row or not role_allows(row[2].role, minimum_role): raise HTTPException(403, "Knowledge base access denied")
    return row

async def authorized_knowledge_bases(db: AsyncSession, user: dict) -> list[KnowledgeBase]:
    stmt = select(KnowledgeBase).join(Workspace).join(Membership, Membership.workspace_id == Workspace.id).where(Membership.user_id == int(user["sub"]))
    return list((await db.scalars(stmt.order_by(KnowledgeBase.id))).all())

async def require_document_access(db: AsyncSession, user: dict, document_id: int, minimum_role: str = "user") -> tuple[Document, Membership]:
    row = (await db.execute(select(Document, Membership).join(Workspace, Document.workspace_id == Workspace.id).join(Membership, Membership.workspace_id == Workspace.id).where(Document.id == document_id, Membership.user_id == int(user["sub"]), Document.organization_id == Membership.organization_id))).first()
    if not row or not role_allows(row[1].role, minimum_role): raise HTTPException(403, "Document access denied")
    return row

async def require_workspace_role(db: AsyncSession, user: dict, workspace_id: int, role: str) -> Membership:
    return await require_workspace_access(db, user, workspace_id, role)
