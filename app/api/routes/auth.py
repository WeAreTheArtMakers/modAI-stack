import hashlib
from datetime import timedelta
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.authorization import ROLE_ORDER, authorized_workspaces
from app.api.deps import current_user, ensure_admin
from app.core.config import get_settings
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models.database import KnowledgeBase, Membership, Organization, User, Workspace
from app.models.schemas import (
    CurrentUserResponse,
    LoginRequest,
    OrganizationAccess,
    RegisterRequest,
    TokenResponse,
    WebSocketTicketRequest,
    WebSocketTicketResponse,
    WorkspaceResponse,
)
from app.services.security import RedisRateLimiter, WebSocketTicketService
from app.services.audit import record_audit_event
router = APIRouter(prefix="/auth", tags=["auth"])
def tokens(user: User):
    s = get_settings()
    return TokenResponse(access_token=create_token(str(user.id), user.role, "access", timedelta(minutes=s.access_token_expire_minutes)))


def _refresh_token(user: User) -> str:
    settings = get_settings()
    return create_token(str(user.id), user.role, "refresh", timedelta(days=settings.refresh_token_expire_days))


def _set_refresh_cookie(response: Response, value: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.refresh_cookie_name,
        value,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/",
    )


async def _limit(request: Request, bucket: str, key: str, limit: int, window: int) -> None:
    limiter = RedisRateLimiter()
    try: await limiter.enforce(bucket, key, limit, window)
    finally: await limiter.close()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if not get_settings().allow_registration:
        raise HTTPException(403, "Registration is disabled")
    await _limit(request, "register", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    if await db.scalar(select(User).where(User.email == req.email)): raise HTTPException(409, "Email already registered")
    # Platform administration and tenant membership are deliberately independent.
    user = User(email=req.email, password_hash=hash_password(req.password), role="user")
    email_suffix = hashlib.sha256(req.email.encode()).hexdigest()[:10]
    organization = Organization(name=f"{req.email}'s organization", slug=f"org-{req.email.split('@')[0].lower()}-{email_suffix}")
    workspace = Workspace(name="Default workspace", slug="default", organization=organization)
    knowledge_base = KnowledgeBase(name="General", slug="general", workspace=workspace)
    db.add_all([user, organization, workspace, knowledge_base])
    await db.flush()
    db.add(Membership(user_id=user.id, organization_id=organization.id, workspace_id=workspace.id, role="admin"))
    record_audit_event(db, action="registration", resource_type="user", actor_user_id=user.id, organization_id=organization.id, workspace_id=workspace.id, resource_id=user.id, request=request)
    await db.commit(); await db.refresh(user); _set_refresh_cookie(response, _refresh_token(user)); return tokens(user)
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await _limit(request, "login", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    user = await db.scalar(select(User).where(User.email == req.email))
    if not user or not verify_password(req.password, user.password_hash):
        record_audit_event(db, action="login", resource_type="session", success=False, metadata={"reason": "invalid_credentials"}, request=request)
        await db.commit()
        raise HTTPException(401, "Invalid email or password")
    record_audit_event(db, action="login", resource_type="session", actor_user_id=user.id, success=True, request=request)
    await db.commit()
    _set_refresh_cookie(response, _refresh_token(user)); return tokens(user)

@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    await _limit(request, "refresh", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    try:
        payload = decode_token(refresh_token or "")
        if payload.get("type") != "refresh": raise ValueError
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Invalid refresh token") from exc
    user = await db.get(User, user_id)
    if not user: raise HTTPException(401, "Invalid refresh token")
    _set_refresh_cookie(response, _refresh_token(user)); return tokens(user)


@router.post("/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie(get_settings().refresh_cookie_name, path="/")


@router.post("/ws-ticket", response_model=WebSocketTicketResponse)
async def issue_websocket_ticket(req: WebSocketTicketRequest, request: Request, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _limit(request, "ws-ticket", str(user["sub"]), get_settings().rate_limit_auth_per_minute, 60)
    if req.scope == "models_pull": ensure_admin(user)
    if req.scope == "indexing":
        if req.workspace_id is None: raise HTTPException(422, "workspace_id is required for indexing")
        from app.api.authorization import require_workspace_access
        await require_workspace_access(db, user, req.workspace_id)
    elif req.workspace_id is not None:
        raise HTTPException(422, "workspace_id is only valid for indexing")
    service = WebSocketTicketService()
    try: ticket = await service.issue(user, req.scope, req.workspace_id)
    finally: await service.close()
    record_audit_event(db, action="websocket_ticket_issued", resource_type=req.scope, actor_user_id=int(user["sub"]), workspace_id=req.workspace_id, request=request)
    await db.commit()
    return WebSocketTicketResponse(ticket=ticket, expires_in=get_settings().websocket_ticket_ttl_seconds)

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
