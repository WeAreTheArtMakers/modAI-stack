from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import ChatSession, Document, KnowledgeBase, Membership, Workspace

ROLE_ORDER = {"user": 1, "manager": 2, "admin": 3}
def role_allows(role: str, minimum: str) -> bool: return ROLE_ORDER.get(role, 0) >= ROLE_ORDER[minimum]

def _workspace_membership_clause():
    return or_(
        Membership.workspace_id == Workspace.id,
        (Membership.workspace_id.is_(None) & (Membership.organization_id == Workspace.organization_id)),
    )

def _stronger_membership(first: Membership, second: Membership) -> Membership:
    return first if role_allows(first.role, second.role) else second

async def require_organization_access(db: AsyncSession, user: dict, organization_id: int, minimum_role: str = "user") -> Membership:
    """Authorize general organization access, including a workspace membership.

    This remains suitable for read/RAG flows.  It intentionally does *not*
    establish organization-wide administrative authority; use
    ``require_organization_admin`` for that stricter boundary.
    """
    membership = await db.scalar(select(Membership).where(Membership.user_id == int(user["sub"]), Membership.organization_id == organization_id, Membership.workspace_id.is_(None)))
    if not membership:
        membership = await db.scalar(select(Membership).where(Membership.user_id == int(user["sub"]), Membership.organization_id == organization_id))
    if not membership or not role_allows(membership.role, minimum_role): raise HTTPException(403, "Organization access denied")
    return membership


async def require_organization_admin(db: AsyncSession, user: dict, organization_id: int) -> Membership:
    """Require an organization-wide tenant administrator membership.

    A membership for a particular workspace is never a fallback here.  Platform
    role checks deliberately live at the route boundary so a platform admin is
    not represented as a synthetic tenant membership.
    """
    membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == int(user["sub"]),
            Membership.organization_id == organization_id,
            Membership.workspace_id.is_(None),
            Membership.role == "admin",
        )
    )
    if not membership:
        raise HTTPException(403, "Organization administrator access denied")
    return membership

async def require_workspace_access(db: AsyncSession, user: dict, workspace_id: int, minimum_role: str = "user") -> Membership:
    rows = list((await db.scalars(
        select(Membership)
        .join(Workspace, Workspace.id == workspace_id)
        .where(
            Membership.user_id == int(user["sub"]),
            _workspace_membership_clause(),
        )
    )).all())
    membership = next((row for row in rows if row.workspace_id == workspace_id), None)
    org_membership = next((row for row in rows if row.workspace_id is None), None)
    if membership and org_membership:
        membership = _stronger_membership(membership, org_membership)
    else:
        membership = membership or org_membership
    if not membership or not role_allows(membership.role, minimum_role): raise HTTPException(403, "Workspace access denied")
    return membership

async def require_knowledge_base_access(db: AsyncSession, user: dict, knowledge_base_id: int, minimum_role: str = "user") -> tuple[KnowledgeBase, Workspace, Membership]:
    rows = (await db.execute(
        select(KnowledgeBase, Workspace, Membership)
        .select_from(KnowledgeBase)
        .join(Workspace, KnowledgeBase.workspace_id == Workspace.id)
        .join(Membership, _workspace_membership_clause())
        .where(KnowledgeBase.id == knowledge_base_id, Membership.user_id == int(user["sub"]))
    )).all()
    if not rows: raise HTTPException(403, "Knowledge base access denied")
    kb, workspace, membership = rows[0]
    for candidate_kb, candidate_workspace, candidate_membership in rows[1:]:
        membership = _stronger_membership(membership, candidate_membership)
    if not role_allows(membership.role, minimum_role): raise HTTPException(403, "Knowledge base access denied")
    return kb, workspace, membership

async def authorized_knowledge_bases(db: AsyncSession, user: dict) -> list[tuple[KnowledgeBase, Membership]]:
    rows = (await db.execute(
        select(KnowledgeBase, Membership)
        .select_from(KnowledgeBase)
        .join(Workspace, KnowledgeBase.workspace_id == Workspace.id)
        .join(Membership, _workspace_membership_clause())
        .where(Membership.user_id == int(user["sub"]))
        .order_by(KnowledgeBase.id)
    )).all()
    selected: dict[int, tuple[KnowledgeBase, Membership]] = {}
    for knowledge_base, membership in rows:
        current = selected.get(knowledge_base.id)
        if current is None or role_allows(membership.role, current[1].role):
            selected[knowledge_base.id] = (knowledge_base, membership)
    return list(selected.values())

async def require_document_access(db: AsyncSession, user: dict, document_id: int, minimum_role: str = "user") -> tuple[Document, Membership]:
    rows = (await db.execute(
        select(Document, Membership)
        .join(Workspace, Document.workspace_id == Workspace.id)
        .join(Membership, _workspace_membership_clause())
        .where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
            Membership.user_id == int(user["sub"]),
            Document.organization_id == Membership.organization_id,
        )
    )).all()
    if not rows: raise HTTPException(403, "Document access denied")
    document, membership = rows[0]
    for candidate_document, candidate_membership in rows[1:]:
        membership = _stronger_membership(membership, candidate_membership)
    if not role_allows(membership.role, minimum_role): raise HTTPException(403, "Document access denied")
    return document, membership

async def authorized_workspaces(db: AsyncSession, user: dict) -> list[tuple[Workspace, int, str]]:
    rows = (await db.execute(
        select(Workspace, Membership.organization_id, Membership.role)
        .join(Membership, _workspace_membership_clause())
        .where(Membership.user_id == int(user["sub"]))
        .order_by(Workspace.id)
    )).all()
    selected: dict[int, tuple[Workspace, int, str]] = {}
    for workspace, organization_id, role in rows:
        current = selected.get(workspace.id)
        if current is None or role_allows(role, current[2]):
            selected[workspace.id] = (workspace, organization_id, role)
    return list(selected.values())

async def resolve_knowledge_base_scope(
    db: AsyncSession,
    user: dict,
    knowledge_base_ids: list[int],
) -> tuple[list[int], tuple[KnowledgeBase, Workspace, Membership]]:
    if not knowledge_base_ids:
        raise HTTPException(400, "Select at least one knowledge base")
    rows = [
        await require_knowledge_base_access(db, user, knowledge_base_id)
        for knowledge_base_id in dict.fromkeys(knowledge_base_ids)
    ]
    scopes = {(row[1].organization_id, row[1].id) for row in rows}
    if len(scopes) != 1:
        raise HTTPException(400, "Selected knowledge bases must share a workspace")
    return [row[0].id for row in rows], rows[0]

async def require_assistant_conversation_access(
    db: AsyncSession,
    user: dict,
    conversation_id: int,
) -> ChatSession:
    conversation = await db.scalar(
        select(ChatSession).where(
            ChatSession.id == conversation_id,
            ChatSession.user_id == int(user["sub"]),
            ChatSession.workspace_id.is_not(None),
        )
    )
    if conversation is None:
        raise HTTPException(404, "Conversation not found")

    await require_workspace_access(
        db,
        user,
        conversation.workspace_id,
    )
    return conversation


async def require_workspace_role(db: AsyncSession, user: dict, workspace_id: int, role: str) -> Membership:
    return await require_workspace_access(db, user, workspace_id, role)
