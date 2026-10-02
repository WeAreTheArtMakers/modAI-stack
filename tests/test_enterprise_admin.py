import hashlib
import os

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# The application module imports the shared engine through the health route.
# Keep this deterministic even when an operator exports a local PostgreSQL URL.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.routes import admin
from app.models.database import AuditEvent, Base, Invitation, KnowledgeBase, Membership, Organization, User, Workspace
from app.models.schemas import (
    InvitationAcceptRequest,
    InvitationCreate,
    MembershipCreate,
    MembershipUpdate,
    PlatformRoleUpdate,
    WorkspaceCreate,
)


@pytest_asyncio.fixture
async def enterprise_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        org_a = Organization(name="Organization A", slug="organization-a")
        org_b = Organization(name="Organization B", slug="organization-b")
        workspace_a = Workspace(name="Engineering", slug="engineering", organization=org_a)
        workspace_b = Workspace(name="Sales", slug="sales", organization=org_b)
        kb_a = KnowledgeBase(name="Engineering", slug="engineering", workspace=workspace_a)
        platform_admin = User(email="platform@example.com", password_hash="x", role="admin")
        tenant_admin = User(email="tenant-admin@example.com", password_hash="x", role="user")
        tenant_manager = User(email="tenant-manager@example.com", password_hash="x", role="user")
        tenant_user = User(email="tenant-user@example.com", password_hash="x", role="user")
        external_user = User(email="invitee@example.com", password_hash="x", role="user")
        db.add_all([org_a, org_b, workspace_a, workspace_b, kb_a, platform_admin, tenant_admin, tenant_manager, tenant_user, external_user])
        await db.flush()
        db.add_all([
            Membership(user_id=tenant_admin.id, organization_id=org_a.id, workspace_id=None, role="admin"),
            Membership(user_id=tenant_manager.id, organization_id=org_a.id, workspace_id=workspace_a.id, role="manager"),
            Membership(user_id=tenant_user.id, organization_id=org_a.id, workspace_id=workspace_a.id, role="user"),
        ])
        await db.commit()
        yield db, {
            "platform": {"sub": str(platform_admin.id), "role": "admin"},
            "tenant_admin": {"sub": str(tenant_admin.id), "role": "user"},
            "tenant_manager": {"sub": str(tenant_manager.id), "role": "user"},
            "tenant_user": {"sub": str(tenant_user.id), "role": "user"},
            "invitee": {"sub": str(external_user.id), "role": "user"},
            "org_a": org_a.id,
            "org_b": org_b.id,
            "workspace_a": workspace_a.id,
            "workspace_b": workspace_b.id,
            "tenant_user_id": tenant_user.id,
            "invitee_id": external_user.id,
            "platform_id": platform_admin.id,
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_platform_roles_are_separate_and_last_platform_admin_is_protected(enterprise_session):
    db, ids = enterprise_session
    users = await admin.list_users(limit=50, offset=0, search=None, user=ids["platform"], db=db)
    assert {user.email for user in users} >= {"platform@example.com", "tenant-admin@example.com"}

    with pytest.raises(HTTPException, match="last platform administrator"):
        await admin.update_platform_role(ids["platform_id"], PlatformRoleUpdate(role="user"), user=ids["platform"], db=db)

    changed = await admin.update_platform_role(ids["tenant_user_id"], PlatformRoleUpdate(role="admin"), user=ids["platform"], db=db)
    assert changed.role == "admin"
    assert (await db.get(Membership, 3)).role == "user"
    assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "platform_role_changed"))


@pytest.mark.asyncio
async def test_tenant_admin_is_limited_to_its_organization_and_manager_cannot_administer(enterprise_session):
    db, ids = enterprise_session
    created = await admin.create_workspace(
        WorkspaceCreate(organization_id=ids["org_a"], name="HR", slug="hr"), user=ids["tenant_admin"], db=db
    )
    assert created.organization_id == ids["org_a"]

    with pytest.raises(HTTPException, match="Organization access denied"):
        await admin.create_workspace(
            WorkspaceCreate(organization_id=ids["org_b"], name="Forbidden", slug="forbidden"), user=ids["tenant_admin"], db=db
        )
    with pytest.raises(HTTPException, match="Organization access denied"):
        await admin.list_memberships(organization_id=ids["org_a"], user=ids["tenant_manager"], db=db)


@pytest.mark.asyncio
async def test_membership_management_cannot_escape_tenant_or_grant_platform_authority(enterprise_session):
    db, ids = enterprise_session
    membership = await admin.create_membership(
        MembershipCreate(user_id=ids["invitee_id"], organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="manager"),
        user=ids["tenant_admin"],
        db=db,
    )
    assert membership.role == "manager"
    assert (await db.get(User, ids["invitee_id"])).role == "user"
    changed = await admin.update_membership(membership.id, MembershipUpdate(role="user"), user=ids["tenant_admin"], db=db)
    assert changed.role == "user"
    await admin.delete_membership(membership.id, user=ids["tenant_admin"], db=db)
    assert await db.get(Membership, membership.id) is None
    audit_actions = list((await db.scalars(select(AuditEvent.action))).all())
    assert {"membership_created", "membership_role_changed", "membership_removed"}.issubset(audit_actions)


@pytest.mark.asyncio
async def test_invitation_is_hashed_single_use_email_bound_and_audited(enterprise_session):
    db, ids = enterprise_session
    created = await admin.create_invitation(
        InvitationCreate(email="invitee@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="manager"),
        user=ids["tenant_admin"],
        db=db,
    )
    invitation = await db.get(Invitation, created.id)
    assert invitation.token_hash == hashlib.sha256(created.delivery_token.encode()).hexdigest()
    assert invitation.token_hash != created.delivery_token
    assert "token_hash" not in created.model_dump()

    with pytest.raises(HTTPException, match="not addressed"):
        await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["tenant_user"], db=db)
    accepted = await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["invitee"], db=db)
    assert accepted.accepted_at is not None
    membership = await db.scalar(select(Membership).where(Membership.user_id == ids["invitee_id"], Membership.organization_id == ids["org_a"]))
    assert membership is not None and membership.role == "manager"
    with pytest.raises(HTTPException, match="already been used"):
        await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["invitee"], db=db)
    assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "invitation_accepted"))


@pytest.mark.asyncio
async def test_invitation_listing_and_revocation_are_tenant_scoped(enterprise_session):
    db, ids = enterprise_session
    created = await admin.create_invitation(
        InvitationCreate(email="new@example.com", organization_id=ids["org_a"]), user=ids["tenant_admin"], db=db
    )
    with pytest.raises(HTTPException, match="Organization access denied"):
        await admin.list_invitations(organization_id=ids["org_b"], user=ids["tenant_admin"], db=db)
    await admin.revoke_invitation(created.id, user=ids["tenant_admin"], db=db)
    assert await db.get(Invitation, created.id) is None
    assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "invitation_revoked"))
