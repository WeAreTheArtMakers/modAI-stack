from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.database import AuditEvent
from app.models.schemas import AuditEventResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventResponse])
async def list_audit_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=100),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del user
    filters = []
    if action: filters.append(AuditEvent.action == action)
    if since: filters.append(AuditEvent.timestamp >= since)
    if until: filters.append(AuditEvent.timestamp <= until)
    return list((await db.scalars(select(AuditEvent).where(*filters).order_by(AuditEvent.id.desc()).offset(offset).limit(limit))).all())
