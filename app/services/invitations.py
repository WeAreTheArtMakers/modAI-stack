"""Shared, secret-safe validation for the existing single-use invitation model."""

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Invitation, Organization, Workspace


def normalize_email(value: str) -> str:
    return value.strip().lower()


def invitation_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def locked_invitation_statement(token_hash: str):
    # PostgreSQL serializes consumption of a token. SQLite ignores FOR UPDATE.
    return select(Invitation).where(Invitation.token_hash == token_hash).with_for_update()


def invitation_expired(invitation: Invitation) -> bool:
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def require_pending_invitation(invitation: Invitation | None) -> Invitation:
    if invitation is None or invitation.accepted_at is not None:
        raise HTTPException(404, "Invitation is invalid or has already been used")
    if invitation_expired(invitation):
        raise HTTPException(410, "Invitation has expired")
    return invitation


async def invitation_target(db: AsyncSession, invitation: Invitation) -> tuple[Organization, Workspace | None]:
    organization = await db.get(Organization, invitation.organization_id)
    if organization is None:
        raise HTTPException(409, "Invitation target is no longer available")
    workspace = None
    if invitation.workspace_id is not None:
        workspace = await db.get(Workspace, invitation.workspace_id)
        if workspace is None or workspace.organization_id != organization.id:
            raise HTTPException(409, "Invitation target is no longer available")
    return organization, workspace
