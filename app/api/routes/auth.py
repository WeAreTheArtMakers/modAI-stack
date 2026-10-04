import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.authorization import ROLE_ORDER, authorized_workspaces
from app.api.deps import current_user, ensure_admin
from app.core.config import get_settings
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_db
from app.models.database import Invitation, KnowledgeBase, Membership, Organization, User, Workspace
from app.models.schemas import (
    CurrentUserResponse,
    InvitationAcceptRequest,
    InvitationSetupInfo,
    InvitationSetupRequest,
    InvitationSetupResponse,
    LoginRequest,
    OrganizationAccess,
    RegisterRequest,
    TokenResponse,
    WebSocketTicketRequest,
    WebSocketTicketResponse,
    WorkspaceResponse,
)
from app.services.security import RefreshSessionService, RedisRateLimiter, WebSocketTicketService
from app.services.audit import record_audit_event
from app.services.invitations import (
    invitation_expired, invitation_target, invitation_token_hash,
    locked_invitation_statement, normalize_email, require_pending_invitation,
)
router = APIRouter(prefix="/auth", tags=["auth"])
def tokens(user: User):
    s = get_settings()
    return TokenResponse(access_token=create_token(str(user.id), user.role, "access", timedelta(minutes=s.access_token_expire_minutes)))


def _refresh_token(user: User, jti: str) -> str:
    settings = get_settings()
    return create_token(str(user.id), user.role, "refresh", timedelta(days=settings.refresh_token_expire_days), jti=jti)


async def _issue_refresh_token(user: User) -> str:
    """Create a refresh JWT and its matching one-time Redis session."""
    settings = get_settings()
    jti = secrets.token_urlsafe(32)
    service = RefreshSessionService()
    try:
        stored = await service.create(jti, user.id, settings.refresh_token_expire_days * 24 * 60 * 60)
    finally:
        await service.close()
    if not stored:
        raise HTTPException(500, "Could not establish refresh session")
    return _refresh_token(user, jti)


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


def _enforce_cookie_mutation_origin(request: Request) -> None:
    """Permit same-origin/no-Origin clients and deliberately configured UI origins.

    Browsers attach ``Origin`` to cross-origin POST requests. Requests without it
    remain available for non-browser local tooling; browser clients still retain
    SameSite cookie protection. This endpoint layer never enables wildcard CORS.
    """
    origin = request.headers.get("origin")
    if not origin:
        return
    normalized_origin = origin.rstrip("/")
    host = request.headers.get("host", request.url.netloc)
    forwarded_scheme = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    scheme = forwarded_scheme if forwarded_scheme in {"http", "https"} else request.url.scheme
    same_origin = f"{scheme}://{host}".rstrip("/")
    settings = get_settings()
    trusted_origins = getattr(settings, "trusted_frontend_origin_set", None)
    if trusted_origins is None:
        trusted_origins = {value.strip().rstrip("/") for value in settings.trusted_frontend_origins.split(",") if value.strip()}
    if normalized_origin == same_origin or normalized_origin in trusted_origins:
        return
    raise HTTPException(403, "Untrusted request origin")


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if not get_settings().allow_registration:
        raise HTTPException(403, "Registration is disabled")
    await _limit(request, "register", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    if await db.scalar(select(User).where(func.lower(User.email) == req.email)): raise HTTPException(409, "Email already registered")
    # Platform administration and tenant membership are deliberately independent.
    user = User(email=req.email, password_hash=hash_password(req.password), role="user")
    email_suffix = hashlib.sha256(req.email.encode()).hexdigest()[:10]
    organization = Organization(name=f"{req.email}'s organization", slug=f"org-{req.email.split('@')[0].lower()}-{email_suffix}")
    workspace = Workspace(name="Default workspace", slug="default", organization=organization)
    knowledge_base = KnowledgeBase(name="General", slug="general", workspace=workspace)
    db.add_all([user, organization, workspace, knowledge_base])
    await db.flush()
    # The creator needs explicit organization-wide administration. A workspace
    # admin alone is intentionally not equivalent to an organization admin.
    db.add(Membership(user_id=user.id, organization_id=organization.id, workspace_id=None, role="admin"))
    record_audit_event(db, action="registration", resource_type="user", actor_user_id=user.id, organization_id=organization.id, workspace_id=workspace.id, resource_id=user.id, request=request)
    await db.commit(); await db.refresh(user); _set_refresh_cookie(response, await _issue_refresh_token(user)); return tokens(user)
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await _limit(request, "login", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    user = await db.scalar(select(User).where(func.lower(User.email) == req.email))
    if not user or not verify_password(req.password, user.password_hash):
        record_audit_event(db, action="login", resource_type="session", success=False, metadata={"reason": "invalid_credentials"}, request=request)
        await db.commit()
        raise HTTPException(401, "Invalid email or password")
    record_audit_event(db, action="login", resource_type="session", actor_user_id=user.id, success=True, request=request)
    await db.commit()
    _set_refresh_cookie(response, await _issue_refresh_token(user)); return tokens(user)


@router.post("/invitations/info", response_model=InvitationSetupInfo)
async def invitation_info(payload: InvitationAcceptRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Reveal only the scope carried by a valid invitation token."""
    await _limit(request, "invitation-info", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    invitation = await db.scalar(select(Invitation).where(Invitation.token_hash == invitation_token_hash(payload.token)))
    if invitation is None:
        raise HTTPException(404, "Invitation is invalid")
    organization, workspace = await invitation_target(db, invitation)
    email = normalize_email(invitation.email)
    account_exists = await db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None
    state = "accepted" if invitation.accepted_at is not None else "expired" if invitation_expired(invitation) else "pending"
    return InvitationSetupInfo(
        status=state, email=email, organization_name=organization.name,
        workspace_name=workspace.name if workspace else None, role=invitation.role,
        expires_at=invitation.expires_at, account_exists=account_exists,
    )


@router.post("/invitations/setup", response_model=InvitationSetupResponse, status_code=201)
async def setup_invited_account(payload: InvitationSetupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create only the account and tenant membership authorized by this token."""
    await _limit(request, "invitation-setup", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    invitation = require_pending_invitation(
        await db.scalar(locked_invitation_statement(invitation_token_hash(payload.token)))
    )
    organization, workspace = await invitation_target(db, invitation)
    email = normalize_email(invitation.email)
    if await db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        raise HTTPException(409, "Account already exists; sign in to accept the invitation")
    account = User(email=email, password_hash=hash_password(payload.password), role="user")
    try:
        db.add(account)
        await db.flush()
        db.add(Membership(
            user_id=account.id, organization_id=invitation.organization_id,
            workspace_id=invitation.workspace_id, role=invitation.role,
        ))
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Invitation account could not be created") from exc
    invitation.accepted_at = datetime.now(timezone.utc)
    record_audit_event(db, action="invite_account_created", resource_type="user", resource_id=account.id,
                       organization_id=invitation.organization_id, workspace_id=invitation.workspace_id, request=request)
    record_audit_event(db, action="invitation_accepted", resource_type="invitation", resource_id=invitation.id,
                       actor_user_id=account.id, organization_id=invitation.organization_id,
                       workspace_id=invitation.workspace_id, request=request)
    await db.commit()
    return InvitationSetupResponse(
        email=email, organization_name=organization.name,
        workspace_name=workspace.name if workspace else None, role=invitation.role,
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, refresh_token: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    _enforce_cookie_mutation_origin(request)
    await _limit(request, "refresh", request.client.host if request.client else "unknown", get_settings().rate_limit_auth_per_minute, 60)
    try:
        payload = decode_token(refresh_token or "")
        if payload.get("type") != "refresh" or not isinstance(payload.get("jti"), str) or not payload["jti"]: raise ValueError
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(401, "Invalid refresh token") from exc
    service = RefreshSessionService()
    try:
        if not await service.consume(payload["jti"], user_id):
            raise HTTPException(401, "Invalid refresh token")
    finally:
        await service.close()
    user = await db.get(User, user_id)
    if not user: raise HTTPException(401, "Invalid refresh token")
    _set_refresh_cookie(response, await _issue_refresh_token(user)); return tokens(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, refresh_token: str | None = Cookie(default=None)):
    _enforce_cookie_mutation_origin(request)
    try:
        payload = decode_token(refresh_token or "")
        if payload.get("type") == "refresh" and isinstance(payload.get("jti"), str) and payload["jti"]:
            service = RefreshSessionService()
            try:
                await service.revoke(payload["jti"])
            finally:
                await service.close()
    except (TypeError, ValueError):
        # Logout is intentionally idempotent: an expired or already-consumed
        # cookie is still cleared without revealing why it was invalid.
        pass
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
    organization_admin_ids = {
        membership.organization_id
        for membership in memberships
        if membership.workspace_id is None and membership.role == "admin"
    }
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
                organization_admin=organization.id in organization_admin_ids,
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
