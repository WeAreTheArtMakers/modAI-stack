"""Structured audit events with an intentionally narrow, secret-safe metadata surface."""
from collections.abc import Mapping

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AuditEvent

SENSITIVE_METADATA_KEYS = {"authorization", "cookie", "password", "token", "secret", "content", "prompt", "body"}


def safe_metadata(metadata: Mapping[str, object] | None = None) -> dict:
    return {
        str(key): value
        for key, value in (metadata or {}).items()
        if str(key).lower() not in SENSITIVE_METADATA_KEYS and isinstance(value, (str, int, float, bool, type(None)))
    }


def record_audit_event(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    actor_user_id: int | None = None,
    organization_id: int | None = None,
    workspace_id: int | None = None,
    resource_id: str | int | None = None,
    success: bool = True,
    metadata: Mapping[str, object] | None = None,
    request: Request | None = None,
) -> AuditEvent:
    event = AuditEvent(
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        success=success,
        metadata_json=safe_metadata(metadata),
        request_id=getattr(request.state, "request_id", None) if request else None,
        source_ip=request.client.host if request and request.client else None,
    )
    db.add(event)
    return event
