"""Enterprise administration APIs.

Platform administration is based on ``User.role``. Tenant administration is
based exclusively on an administrator membership in the target organization;
neither form of authority is silently converted into the other.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_organization_access
from app.api.deps import current_user, ensure_admin
from app.api.routes.health import ready
from app.core.config import get_settings
from app.db.session import get_db
from app.models.database import Document, Invitation, KnowledgeBase, Membership, Organization, User, Workspace
from app.models.schemas import (
    AdminUserResponse,
    InvitationAcceptRequest,
    InvitationCreate,
    InvitationCreatedResponse,
    InvitationResponse,
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
    OrganizationAdminResponse,
    PlatformRoleUpdate,
    PlatformStatusResponse,
    WorkspaceAdminResponse,
    WorkspaceCreate,
    WorkspaceUpdate,
)
from app.services.audit import record_audit_event

router = APIRouter(prefix="/admin", tags=["enterprise administration"])


def _is_platform_admin(user: dict) -> bool:
    return user.get("role") == "admin"


async def _require_organization_admin(db: AsyncSession, user: dict, organization_id: int) -> None:
    if _is_platform_admin(user):
        return
    await require_organization_access(db, user, organization_id, "admin")


async def _organization_or_404(db: AsyncSession, organization_id: int) -> Organization:
    organization = await db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(404, "Organization not found")
    return organization


async def _workspace_or_404(db: AsyncSession, workspace_id: int) -> Workspace:
    workspace = await db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    return workspace


async def _workspace_for_organization(db: AsyncSession, workspace_id: int | None, organization_id: int) -> Workspace | None:
    if workspace_id is None:
        return None
    workspace = await _workspace_or_404(db, workspace_id)
    if workspace.organization_id != organization_id:
        raise HTTPException(422, "Workspace does not belong to the organization")
    return workspace


async def _organization_response(db: AsyncSession, organization: Organization) -> OrganizationAdminResponse:
    workspace_count = await db.scalar(select(func.count()).select_from(Workspace).where(Workspace.organization_id == organization.id))
    knowledge_base_count = await db.scalar(
        select(func.count()).select_from(KnowledgeBase).join(Workspace).where(Workspace.organization_id == organization.id)
    )
    document_count = await db.scalar(select(func.count()).select_from(Document).where(Document.organization_id == organization.id))
    member_count = await db.scalar(
        select(func.count(func.distinct(Membership.user_id))).where(Membership.organization_id == organization.id)
    )
    return OrganizationAdminResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        created_at=organization.created_at,
        workspace_count=workspace_count or 0,
        knowledge_base_count=knowledge_base_count or 0,
        document_count=document_count or 0,
        member_count=member_count or 0,
    )


def _membership_response(membership: Membership, account: User) -> MembershipResponse:
    return MembershipResponse(
        id=membership.id,
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        workspace_id=membership.workspace_id,
        role=membership.role,
        user_email=account.email,
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, min_length=1, max_length=320),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_admin(user)
    statement = select(User).order_by(User.id).offset(offset).limit(limit)
    if search:
        statement = statement.where(User.email.ilike(f"%{search.strip()}%"))
    return list((await db.scalars(statement)).all())


@router.patch("/users/{user_id}/platform-role", response_model=AdminUserResponse)
async def update_platform_role(
    user_id: int,
    payload: PlatformRoleUpdate,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_admin(user)
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == "admin" and payload.role != "admin":
        admin_count = await db.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
        if (admin_count or 0) <= 1:
            raise HTTPException(409, "The last platform administrator cannot be demoted")
    if target.role != payload.role:
        previous_role = target.role
        target.role = payload.role
        record_audit_event(
            db,
            action="platform_role_changed",
            resource_type="user",
            resource_id=target.id,
            actor_user_id=int(user["sub"]),
            metadata={"from_role": previous_role, "to_role": payload.role},
        )
        await db.commit()
        await db.refresh(target)
    return target


@router.get("/organizations", response_model=list[OrganizationAdminResponse])
async def list_organizations(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    if _is_platform_admin(user):
        organizations = list((await db.scalars(select(Organization).order_by(Organization.id))).all())
    else:
        organization_ids = select(Membership.organization_id).where(
            Membership.user_id == int(user["sub"]), Membership.role == "admin"
        ).distinct()
        organizations = list((await db.scalars(select(Organization).where(Organization.id.in_(organization_ids)).order_by(Organization.id))).all())
    return [await _organization_response(db, organization) for organization in organizations]


@router.get("/organizations/{organization_id}", response_model=OrganizationAdminResponse)
async def get_organization(organization_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _require_organization_admin(db, user, organization_id)
    return await _organization_response(db, await _organization_or_404(db, organization_id))


@router.get("/workspaces", response_model=list[WorkspaceAdminResponse])
async def list_admin_workspaces(
    organization_id: int | None = Query(default=None, gt=0),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if organization_id is not None:
        await _require_organization_admin(db, user, organization_id)
        statement = select(Workspace).where(Workspace.organization_id == organization_id).order_by(Workspace.id)
    elif _is_platform_admin(user):
        statement = select(Workspace).order_by(Workspace.id)
    else:
        organization_ids = select(Membership.organization_id).where(
            Membership.user_id == int(user["sub"]), Membership.role == "admin"
        ).distinct()
        statement = select(Workspace).where(Workspace.organization_id.in_(organization_ids)).order_by(Workspace.id)
    return list((await db.scalars(statement)).all())


@router.post("/workspaces", response_model=WorkspaceAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(payload: WorkspaceCreate, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _require_organization_admin(db, user, payload.organization_id)
    await _organization_or_404(db, payload.organization_id)
    existing = await db.scalar(select(Workspace).where(Workspace.organization_id == payload.organization_id, Workspace.slug == payload.slug))
    if existing:
        raise HTTPException(409, "Workspace slug already exists in this organization")
    workspace = Workspace(organization_id=payload.organization_id, name=payload.name.strip(), slug=payload.slug)
    db.add(workspace)
    await db.flush()
    record_audit_event(db, action="workspace_created", resource_type="workspace", resource_id=workspace.id, actor_user_id=int(user["sub"]), organization_id=workspace.organization_id)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceAdminResponse)
async def update_workspace(workspace_id: int, payload: WorkspaceUpdate, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    workspace = await _workspace_or_404(db, workspace_id)
    await _require_organization_admin(db, user, workspace.organization_id)
    if payload.slug and payload.slug != workspace.slug:
        existing = await db.scalar(select(Workspace).where(Workspace.organization_id == workspace.organization_id, Workspace.slug == payload.slug, Workspace.id != workspace.id))
        if existing:
            raise HTTPException(409, "Workspace slug already exists in this organization")
        workspace.slug = payload.slug
    if payload.name:
        workspace.name = payload.name.strip()
    record_audit_event(db, action="workspace_updated", resource_type="workspace", resource_id=workspace.id, actor_user_id=int(user["sub"]), organization_id=workspace.organization_id)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.get("/memberships", response_model=list[MembershipResponse])
async def list_memberships(
    organization_id: int = Query(gt=0),
    workspace_id: int | None = Query(default=None, gt=0),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_organization_admin(db, user, organization_id)
    await _workspace_for_organization(db, workspace_id, organization_id)
    statement = select(Membership, User).join(User).where(Membership.organization_id == organization_id).order_by(Membership.id)
    if workspace_id is not None:
        statement = statement.where(Membership.workspace_id == workspace_id)
    return [_membership_response(membership, account) for membership, account in (await db.execute(statement)).all()]


@router.post("/memberships", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
async def create_membership(payload: MembershipCreate, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _require_organization_admin(db, user, payload.organization_id)
    await _organization_or_404(db, payload.organization_id)
    await _workspace_for_organization(db, payload.workspace_id, payload.organization_id)
    account = await db.get(User, payload.user_id)
    if not account:
        raise HTTPException(404, "User not found")
    statement = select(Membership).where(Membership.user_id == payload.user_id, Membership.organization_id == payload.organization_id)
    statement = statement.where(Membership.workspace_id == payload.workspace_id) if payload.workspace_id else statement.where(Membership.workspace_id.is_(None))
    if await db.scalar(statement):
        raise HTTPException(409, "Membership already exists")
    membership = Membership(**payload.model_dump())
    db.add(membership)
    await db.flush()
    record_audit_event(db, action="membership_created", resource_type="membership", resource_id=membership.id, actor_user_id=int(user["sub"]), organization_id=membership.organization_id, workspace_id=membership.workspace_id, metadata={"role": membership.role, "member_user_id": membership.user_id})
    await db.commit()
    return _membership_response(membership, account)


@router.patch("/memberships/{membership_id}", response_model=MembershipResponse)
async def update_membership(membership_id: int, payload: MembershipUpdate, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    membership = await db.get(Membership, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")
    await _require_organization_admin(db, user, membership.organization_id)
    account = await db.get(User, membership.user_id)
    if not account:
        raise HTTPException(404, "User not found")
    previous_role = membership.role
    membership.role = payload.role
    record_audit_event(db, action="membership_role_changed", resource_type="membership", resource_id=membership.id, actor_user_id=int(user["sub"]), organization_id=membership.organization_id, workspace_id=membership.workspace_id, metadata={"from_role": previous_role, "to_role": membership.role, "member_user_id": membership.user_id})
    await db.commit()
    await db.refresh(membership)
    return _membership_response(membership, account)


@router.delete("/memberships/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_membership(membership_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    membership = await db.get(Membership, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")
    await _require_organization_admin(db, user, membership.organization_id)
    record_audit_event(db, action="membership_removed", resource_type="membership", resource_id=membership.id, actor_user_id=int(user["sub"]), organization_id=membership.organization_id, workspace_id=membership.workspace_id, metadata={"member_user_id": membership.user_id})
    await db.delete(membership)
    await db.commit()


@router.get("/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    organization_id: int = Query(gt=0),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_organization_admin(db, user, organization_id)
    return list((await db.scalars(select(Invitation).where(Invitation.organization_id == organization_id).order_by(Invitation.id.desc()))).all())


@router.post("/invitations", response_model=InvitationCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_invitation(payload: InvitationCreate, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _require_organization_admin(db, user, payload.organization_id)
    await _organization_or_404(db, payload.organization_id)
    await _workspace_for_organization(db, payload.workspace_id, payload.organization_id)
    delivery_token = secrets.token_urlsafe(32)
    invitation = Invitation(
        email=str(payload.email).lower(),
        organization_id=payload.organization_id,
        workspace_id=payload.workspace_id,
        role=payload.role,
        token_hash=hashlib.sha256(delivery_token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours),
        created_by_user_id=int(user["sub"]),
    )
    db.add(invitation)
    await db.flush()
    record_audit_event(db, action="invitation_created", resource_type="invitation", resource_id=invitation.id, actor_user_id=int(user["sub"]), organization_id=invitation.organization_id, workspace_id=invitation.workspace_id, metadata={"role": invitation.role})
    await db.commit()
    await db.refresh(invitation)
    return InvitationCreatedResponse(
        **InvitationResponse.model_validate(invitation).model_dump(),
        delivery_token=delivery_token,
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(invitation_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    invitation = await db.get(Invitation, invitation_id)
    if not invitation:
        raise HTTPException(404, "Invitation not found")
    await _require_organization_admin(db, user, invitation.organization_id)
    if invitation.accepted_at is not None:
        raise HTTPException(409, "Accepted invitations cannot be revoked")
    record_audit_event(db, action="invitation_revoked", resource_type="invitation", resource_id=invitation.id, actor_user_id=int(user["sub"]), organization_id=invitation.organization_id, workspace_id=invitation.workspace_id)
    await db.delete(invitation)
    await db.commit()


@router.post("/invitations/accept", response_model=InvitationResponse)
async def accept_invitation(payload: InvitationAcceptRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    invitation = await db.scalar(select(Invitation).where(Invitation.token_hash == token_hash))
    if not invitation or invitation.accepted_at is not None:
        raise HTTPException(404, "Invitation is invalid or has already been used")
    expires_at = invitation.expires_at.replace(tzinfo=None) if invitation.expires_at.tzinfo else invitation.expires_at
    if expires_at <= datetime.utcnow():
        raise HTTPException(410, "Invitation has expired")
    account = await db.get(User, int(user["sub"]))
    if not account or account.email.lower() != invitation.email.lower():
        raise HTTPException(403, "Invitation is not addressed to this account")
    statement = select(Membership).where(Membership.user_id == account.id, Membership.organization_id == invitation.organization_id)
    statement = statement.where(Membership.workspace_id == invitation.workspace_id) if invitation.workspace_id else statement.where(Membership.workspace_id.is_(None))
    if not await db.scalar(statement):
        db.add(Membership(user_id=account.id, organization_id=invitation.organization_id, workspace_id=invitation.workspace_id, role=invitation.role))
    invitation.accepted_at = datetime.now(timezone.utc)
    record_audit_event(db, action="invitation_accepted", resource_type="invitation", resource_id=invitation.id, actor_user_id=account.id, organization_id=invitation.organization_id, workspace_id=invitation.workspace_id)
    await db.commit()
    await db.refresh(invitation)
    return invitation


@router.get("/platform", response_model=PlatformStatusResponse)
async def platform_status(user=Depends(current_user)):
    ensure_admin(user)
    settings = get_settings()
    return PlatformStatusResponse(
        registration_enabled=settings.allow_registration,
        configured_provider="ollama",
        configured_model=settings.ollama_model,
        embedding_model=settings.embedding_model,
        readiness=await ready(),
    )
