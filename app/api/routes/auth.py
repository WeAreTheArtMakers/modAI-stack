import hashlib
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.authorization import ROLE_ORDER, authorized_workspaces
from app.api.deps import current_user
from app.core.config import get_settings
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models.database import KnowledgeBase, Membership, Organization, User, Workspace
from app.models.schemas import (
    CurrentUserResponse,
    LoginRequest,
    OrganizationAccess,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    WorkspaceResponse,
)
router = APIRouter(prefix="/auth", tags=["auth"])
def tokens(user: User):
    s = get_settings()
    return TokenResponse(access_token=create_token(str(user.id), user.role, "access", timedelta(minutes=s.access_token_expire_minutes)), refresh_token=create_token(str(user.id), user.role, "refresh", timedelta(days=s.refresh_token_expire_days)))
@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(User).where(User.email == req.email)): raise HTTPException(409, "Email already registered")
    user = User(email=req.email, password_hash=hash_password(req.password), role="admin")
    email_suffix = hashlib.sha256(req.email.encode()).hexdigest()[:10]
    organization = Organization(name=f"{req.email}'s organization", slug=f"org-{req.email.split('@')[0].lower()}-{email_suffix}")
    workspace = Workspace(name="Default workspace", slug="default", organization=organization)
    knowledge_base = KnowledgeBase(name="General", slug="general", workspace=workspace)
    db.add_all([user, organization, workspace, knowledge_base])
    await db.flush()
    db.add(Membership(user_id=user.id, organization_id=organization.id, workspace_id=workspace.id, role="admin"))
    await db.commit(); await db.refresh(user); return tokens(user)
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == req.email))
    if not user or not verify_password(req.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    return tokens(user)

@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh": raise ValueError
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Invalid refresh token") from exc
    user = await db.get(User, user_id)
    if not user: raise HTTPException(401, "Invalid refresh token")
    return tokens(user)

@router.get("/me", response_model=CurrentUserResponse)
async def me(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    account = await db.get(User, int(user["sub"]))
    if not account: raise HTTPException(401, "User no longer exists")

    memberships = list((await db.scalars(
        select(Membership).where(Membership.user_id == account.id)
    )).all())
    organization_ids = {membership.organization_id for membership in memberships}
    organizations = list((await db.scalars(
        select(Organization).where(Organization.id.in_(organization_ids)).order_by(Organization.id)
    )).all()) if organization_ids else []
    organization_roles: dict[int, str] = {}
    for membership in memberships:
        current = organization_roles.get(membership.organization_id)
        if current is None or ROLE_ORDER.get(membership.role, 0) > ROLE_ORDER.get(current, 0):
            organization_roles[membership.organization_id] = membership.role

    workspace_rows = await authorized_workspaces(db, user)
    return CurrentUserResponse(
        id=account.id,
        email=account.email,
        role=account.role,
        organizations=[
            OrganizationAccess(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                membership_role=organization_roles[organization.id],
            )
            for organization in organizations
        ],
        workspaces=[
            WorkspaceResponse(
                id=workspace.id,
                organization_id=organization_id,
                name=workspace.name,
                slug=workspace.slug,
                membership_role=role,
            )
            for workspace, organization_id, role in workspace_rows
        ],
    )
