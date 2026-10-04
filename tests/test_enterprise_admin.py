import hashlib
import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# The application module imports the shared engine through the health route.
# Keep this deterministic even when an operator exports a local PostgreSQL URL.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.routes import admin, auth
from app.core.security import verify_password
from app.models.database import AuditEvent, Base, Invitation, KnowledgeBase, Membership, Organization, User, Workspace
from app.models.schemas import (
    InvitationAcceptRequest,
    InvitationCreate,
    InvitationSetupRequest,
    MembershipCreate,
    MembershipUpdate,
    OrganizationCreate,
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
        workspace_admin = User(email="workspace-admin@example.com", password_hash="x", role="user")
        external_user = User(email="invitee@example.com", password_hash="x", role="user")
        db.add_all([org_a, org_b, workspace_a, workspace_b, kb_a, platform_admin, tenant_admin, tenant_manager, tenant_user, workspace_admin, external_user])
        await db.flush()
        db.add_all([
            Membership(user_id=tenant_admin.id, organization_id=org_a.id, workspace_id=None, role="admin"),
            Membership(user_id=tenant_manager.id, organization_id=org_a.id, workspace_id=workspace_a.id, role="manager"),
            Membership(user_id=tenant_user.id, organization_id=org_a.id, workspace_id=workspace_a.id, role="user"),
            Membership(user_id=workspace_admin.id, organization_id=org_a.id, workspace_id=workspace_a.id, role="admin"),
        ])
        await db.commit()
        yield db, {
            "platform": {"sub": str(platform_admin.id), "role": "admin"},
            "tenant_admin": {"sub": str(tenant_admin.id), "role": "user"},
            "tenant_manager": {"sub": str(tenant_manager.id), "role": "user"},
            "tenant_user": {"sub": str(tenant_user.id), "role": "user"},
            "workspace_admin": {"sub": str(workspace_admin.id), "role": "user"},
            "invitee": {"sub": str(external_user.id), "role": "user"},
            "org_a": org_a.id,
            "org_b": org_b.id,
            "workspace_a": workspace_a.id,
            "workspace_b": workspace_b.id,
            "tenant_user_id": tenant_user.id,
            "workspace_admin_id": workspace_admin.id,
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

    with pytest.raises(HTTPException, match="Organization administrator access denied"):
        await admin.create_workspace(
            WorkspaceCreate(organization_id=ids["org_b"], name="Forbidden", slug="forbidden"), user=ids["tenant_admin"], db=db
        )
    with pytest.raises(HTTPException, match="Organization administrator access denied"):
        await admin.list_memberships(organization_id=ids["org_a"], user=ids["tenant_manager"], db=db)


@pytest.mark.asyncio
async def test_only_platform_admin_can_seed_first_company_organization(enterprise_session):
    db, ids = enterprise_session
    with pytest.raises(HTTPException, match="Admin role required"):
        await admin.create_organization(OrganizationCreate(name="New Company", slug="new-company"), user=ids["tenant_admin"], db=db)
    created = await admin.create_organization(OrganizationCreate(name="New Company", slug="new-company"), user=ids["platform"], db=db)
    assert created.name == "New Company" and created.member_count == 0
    with pytest.raises(HTTPException, match="slug already exists"):
        await admin.create_organization(OrganizationCreate(name="Duplicate", slug="new-company"), user=ids["platform"], db=db)
    assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "organization_created"))


@pytest.mark.asyncio
async def test_membership_management_cannot_escape_tenant_or_grant_platform_authority(enterprise_session):
    db, ids = enterprise_session
    membership = await admin.create_membership(
        MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="manager"),
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
    with pytest.raises(HTTPException, match="Organization administrator access denied"):
        await admin.list_invitations(organization_id=ids["org_b"], user=ids["tenant_admin"], db=db)
    await admin.revoke_invitation(created.id, user=ids["tenant_admin"], db=db)
    assert await db.get(Invitation, created.id) is None
    assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "invitation_revoked"))


@pytest.mark.asyncio
async def test_last_organization_admin_cannot_be_demoted_or_removed(enterprise_session):
    db, ids = enterprise_session
    membership = await db.scalar(select(Membership).where(Membership.user_id == int(ids["tenant_admin"]["sub"])))
    assert membership is not None and membership.workspace_id is None and membership.role == "admin"

    with pytest.raises(HTTPException, match="last organization administrator"):
        await admin.update_membership(membership.id, MembershipUpdate(role="manager"), user=ids["tenant_admin"], db=db)
    with pytest.raises(HTTPException, match="last organization administrator"):
        await admin.delete_membership(membership.id, user=ids["tenant_admin"], db=db)


@pytest.mark.asyncio
async def test_one_of_two_organization_admins_can_be_changed_or_removed(enterprise_session):
    db, ids = enterprise_session
    second = await admin.create_membership(
        MembershipCreate(user_email="tenant-user@example.com", organization_id=ids["org_a"], role="admin"),
        user=ids["tenant_admin"],
        db=db,
    )
    await admin.create_membership(
        MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], role="admin"),
        user=ids["tenant_admin"],
        db=db,
    )
    original = await db.scalar(select(Membership).where(Membership.user_id == int(ids["tenant_admin"]["sub"])))
    assert original is not None
    changed = await admin.update_membership(original.id, MembershipUpdate(role="manager"), user=ids["tenant_admin"], db=db)
    assert changed.role == "manager"
    await admin.delete_membership(second.id, user=ids["tenant_user"], db=db)


@pytest.mark.asyncio
async def test_workspace_admin_is_not_an_organization_administrator(enterprise_session):
    db, ids = enterprise_session
    with pytest.raises(HTTPException, match="Organization administrator access denied"):
        await admin.create_workspace(
            WorkspaceCreate(organization_id=ids["org_a"], name="Forbidden", slug="forbidden"),
            user=ids["workspace_admin"],
            db=db,
        )
    assert await admin.list_organizations(user=ids["workspace_admin"], db=db) == []


@pytest.mark.asyncio
async def test_duplicate_organization_and_workspace_memberships_are_rejected(enterprise_session):
    db, ids = enterprise_session
    await admin.create_membership(
        MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], role="user"),
        user=ids["tenant_admin"],
        db=db,
    )
    with pytest.raises(HTTPException, match="Membership already exists"):
        await admin.create_membership(
            MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], role="user"),
            user=ids["tenant_admin"],
            db=db,
        )
    await admin.create_membership(
        MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="user"),
        user=ids["tenant_admin"],
        db=db,
    )
    with pytest.raises(HTTPException, match="Membership already exists"):
        await admin.create_membership(
            MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="user"),
            user=ids["tenant_admin"],
            db=db,
        )


@pytest.mark.asyncio
async def test_membership_integrity_error_becomes_safe_conflict(enterprise_session, monkeypatch):
    db, ids = enterprise_session

    async def duplicate_flush():
        raise IntegrityError("INSERT memberships", {}, Exception("duplicate"))

    monkeypatch.setattr(db, "flush", duplicate_flush)
    with pytest.raises(HTTPException, match="Membership already exists") as error:
        await admin.create_membership(
            MembershipCreate(user_email="invitee@example.com", organization_id=ids["org_a"], role="user"),
            user=ids["tenant_admin"],
            db=db,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_invitation_expiration_and_email_normalization_are_enforced(enterprise_session):
    db, ids = enterprise_session
    created = await admin.create_invitation(
        InvitationCreate(email="INVITEE@example.com", organization_id=ids["org_a"]), user=ids["tenant_admin"], db=db
    )
    invitation = await db.get(Invitation, created.id)
    assert invitation is not None
    invitation.email = "  INVITEE@EXAMPLE.COM  "
    await db.commit()
    accepted = await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["invitee"], db=db)
    assert accepted.accepted_at is not None

    expired = await admin.create_invitation(
        InvitationCreate(email="invitee@example.com", organization_id=ids["org_a"]), user=ids["tenant_admin"], db=db
    )
    expired_row = await db.get(Invitation, expired.id)
    assert expired_row is not None
    expired_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    with pytest.raises(HTTPException, match="expired"):
        await admin.accept_invitation(InvitationAcceptRequest(token=expired.delivery_token), user=ids["invitee"], db=db)


@pytest.mark.asyncio
async def test_invitation_lock_is_compiled_for_postgresql_and_replay_consumes_once(enterprise_session):
    db, ids = enterprise_session
    statement = admin._locked_invitation_statement("hash")
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))

    created = await admin.create_invitation(
        InvitationCreate(email="invitee@example.com", organization_id=ids["org_a"]), user=ids["tenant_admin"], db=db
    )
    await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["invitee"], db=db)
    with pytest.raises(HTTPException, match="already been used"):
        await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["invitee"], db=db)
    accepted_events = list((await db.scalars(select(AuditEvent).where(AuditEvent.action == "invitation_accepted"))).all())
    assert len(accepted_events) == 1


@pytest.mark.asyncio
async def test_database_partial_index_rejects_duplicate_organization_memberships(enterprise_session):
    db, ids = enterprise_session
    db.add(Membership(user_id=int(ids["tenant_admin"]["sub"]), organization_id=ids["org_a"], workspace_id=None, role="admin"))
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


def _invitation_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/auth/invitations/setup",
                    "headers": [], "client": ("127.0.0.1", 1)})


@pytest.mark.asyncio
async def test_tenant_invitation_authorization_and_workspace_scope(enterprise_session):
    db, ids = enterprise_session
    own = await admin.create_invitation(
        InvitationCreate(email="new@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="manager"),
        user=ids["tenant_admin"], db=db,
    )
    assert own.workspace_id == ids["workspace_a"] and own.role == "manager"
    with pytest.raises(HTTPException, match="Organization administrator access denied"):
        await admin.create_invitation(InvitationCreate(email="new@example.com", organization_id=ids["org_b"]), user=ids["tenant_admin"], db=db)
    with pytest.raises(HTTPException, match="Workspace does not belong"):
        await admin.create_invitation(InvitationCreate(email="new@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_b"]), user=ids["tenant_admin"], db=db)
    with pytest.raises(HTTPException, match="Organization administrator access denied"):
        await admin.create_invitation(InvitationCreate(email="new@example.com", organization_id=ids["org_a"]), user=ids["tenant_manager"], db=db)


@pytest.mark.asyncio
async def test_new_invitee_creates_only_company_account_and_membership_when_public_registration_is_disabled(enterprise_session, monkeypatch):
    from types import SimpleNamespace

    db, ids = enterprise_session
    async def no_limit(*_args, **_kwargs): return None
    monkeypatch.setattr(auth, "_limit", no_limit)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(allow_registration=False, rate_limit_auth_per_minute=10))
    created = await admin.create_invitation(
        InvitationCreate(email="NEW.PERSON@EXAMPLE.COM", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="manager"),
        user=ids["tenant_admin"], db=db,
    )
    request = _invitation_request()
    info = await auth.invitation_info(InvitationAcceptRequest(token=created.delivery_token), request=request, db=db)
    assert info.status == "pending" and info.email == "new.person@example.com"
    assert info.account_exists is False and info.organization_name == "Organization A" and info.workspace_name == "Engineering"
    result = await auth.setup_invited_account(InvitationSetupRequest(token=created.delivery_token, password="company-chosen-password"), request=request, db=db)
    assert result.email == "new.person@example.com" and result.role == "manager"
    account = await db.scalar(select(User).where(User.email == result.email))
    assert account is not None and account.role == "user" and verify_password("company-chosen-password", account.password_hash)
    assert account.password_hash != "company-chosen-password"
    memberships = list((await db.scalars(select(Membership).where(Membership.user_id == account.id))).all())
    assert len(memberships) == 1
    assert (memberships[0].organization_id, memberships[0].workspace_id, memberships[0].role) == (ids["org_a"], ids["workspace_a"], "manager")
    assert (await db.scalar(select(Organization).where(Organization.name.contains("new.person")))) is None
    assert len(list((await db.scalars(select(Organization))).all())) == 2
    assert len(list((await db.scalars(select(Workspace))).all())) == 2
    assert len(list((await db.scalars(select(KnowledgeBase))).all())) == 1
    assert (await auth.invitation_info(InvitationAcceptRequest(token=created.delivery_token), request=request, db=db)).status == "accepted"
    with pytest.raises(HTTPException, match="already been used"):
        await auth.setup_invited_account(InvitationSetupRequest(token=created.delivery_token, password="another-password"), request=request, db=db)
    actions = set((await db.scalars(select(AuditEvent.action))).all())
    assert {"invitation_created", "invite_account_created", "invitation_accepted"}.issubset(actions)


@pytest.mark.asyncio
async def test_new_invitee_can_receive_organization_wide_membership_without_personal_tenant(enterprise_session, monkeypatch):
    db, ids = enterprise_session
    async def no_limit(*_args, **_kwargs): return None
    monkeypatch.setattr(auth, "_limit", no_limit)
    created = await admin.create_invitation(InvitationCreate(email="org-member@example.com", organization_id=ids["org_a"], role="user"), user=ids["tenant_admin"], db=db)
    await auth.setup_invited_account(InvitationSetupRequest(token=created.delivery_token, password="employee-password"), request=_invitation_request(), db=db)
    account = await db.scalar(select(User).where(User.email == "org-member@example.com"))
    memberships = list((await db.scalars(select(Membership).where(Membership.user_id == account.id))).all())
    assert len(memberships) == 1 and memberships[0].workspace_id is None
    assert memberships[0].organization_id == ids["org_a"] and memberships[0].role == "user"
    assert len(list((await db.scalars(select(Organization))).all())) == 2


@pytest.mark.asyncio
async def test_existing_account_cannot_be_reset_by_invite_token_and_membership_role_is_preserved(enterprise_session, monkeypatch):
    db, ids = enterprise_session
    async def no_limit(*_args, **_kwargs): return None
    monkeypatch.setattr(auth, "_limit", no_limit)
    account = await db.get(User, ids["invitee_id"])
    old_hash = account.password_hash
    first = await admin.create_invitation(InvitationCreate(email="invitee@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="user"), user=ids["tenant_admin"], db=db)
    info = await auth.invitation_info(InvitationAcceptRequest(token=first.delivery_token), request=_invitation_request(), db=db)
    assert info.account_exists is True
    with pytest.raises(HTTPException, match="Account already exists"):
        await auth.setup_invited_account(InvitationSetupRequest(token=first.delivery_token, password="attacker-password"), request=_invitation_request(), db=db)
    assert (await db.get(User, account.id)).password_hash == old_hash
    await admin.accept_invitation(InvitationAcceptRequest(token=first.delivery_token), user=ids["invitee"], db=db)
    second = await admin.create_invitation(InvitationCreate(email="invitee@example.com", organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="admin"), user=ids["tenant_admin"], db=db)
    await admin.accept_invitation(InvitationAcceptRequest(token=second.delivery_token), user=ids["invitee"], db=db)
    memberships = list((await db.scalars(select(Membership).where(Membership.user_id == account.id, Membership.organization_id == ids["org_a"]))).all())
    assert len(memberships) == 1 and memberships[0].role == "user"
    assert (await db.get(User, account.id)).role == "user" and account.password_hash == old_hash


@pytest.mark.asyncio
async def test_invite_setup_invalid_revoked_and_expired_tokens(enterprise_session, monkeypatch):
    db, ids = enterprise_session
    async def no_limit(*_args, **_kwargs): return None
    monkeypatch.setattr(auth, "_limit", no_limit)
    request = _invitation_request()
    with pytest.raises(HTTPException, match="invalid"):
        await auth.setup_invited_account(InvitationSetupRequest(token="x" * 40, password="valid-password"), request=request, db=db)
    expired = await admin.create_invitation(InvitationCreate(email="later@example.com", organization_id=ids["org_a"]), user=ids["tenant_admin"], db=db)
    row = await db.get(Invitation, expired.id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    assert (await auth.invitation_info(InvitationAcceptRequest(token=expired.delivery_token), request=request, db=db)).status == "expired"
    with pytest.raises(HTTPException, match="expired"):
        await auth.setup_invited_account(InvitationSetupRequest(token=expired.delivery_token, password="valid-password"), request=request, db=db)
    revoked = await admin.create_invitation(InvitationCreate(email="revoked@example.com", organization_id=ids["org_a"]), user=ids["tenant_admin"], db=db)
    await admin.revoke_invitation(revoked.id, user=ids["tenant_admin"], db=db)
    with pytest.raises(HTTPException, match="invalid"):
        await auth.invitation_info(InvitationAcceptRequest(token=revoked.delivery_token), request=request, db=db)


@pytest.mark.asyncio
async def test_concurrent_membership_winner_cannot_be_duplicated_or_role_escalated(enterprise_session, monkeypatch):
    db, ids = enterprise_session
    account = await db.get(User, ids["invitee_id"])
    winner = Membership(user_id=account.id, organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="user")
    db.add(winner)
    await db.commit()
    created = await admin.create_invitation(InvitationCreate(email=account.email, organization_id=ids["org_a"], workspace_id=ids["workspace_a"], role="admin"), user=ids["tenant_admin"], db=db)
    original_scalar = db.scalar
    original_flush = db.flush
    membership_checks = 0
    async def racing_scalar(statement, *args, **kwargs):
        nonlocal membership_checks
        if "FROM memberships" in str(statement) and membership_checks == 0:
            membership_checks += 1
            return None  # The other transaction commits between check and insert.
        return await original_scalar(statement, *args, **kwargs)
    async def duplicate_flush(*_args, **_kwargs):
        raise IntegrityError("INSERT memberships", {}, Exception("duplicate"))
    monkeypatch.setattr(db, "scalar", racing_scalar)
    monkeypatch.setattr(db, "flush", duplicate_flush)
    await admin.accept_invitation(InvitationAcceptRequest(token=created.delivery_token), user=ids["invitee"], db=db)
    monkeypatch.setattr(db, "scalar", original_scalar)
    monkeypatch.setattr(db, "flush", original_flush)
    memberships = list((await db.scalars(select(Membership).where(Membership.user_id == account.id, Membership.organization_id == ids["org_a"]))).all())
    assert len(memberships) == 1 and memberships[0].role == "user"
