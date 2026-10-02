from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import authorized_workspaces
from app.api.deps import current_user
from app.db.session import get_db
from app.models.schemas import WorkspaceResponse

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    return [
        WorkspaceResponse(
            id=workspace.id,
            organization_id=organization_id,
            name=workspace.name,
            slug=workspace.slug,
            membership_role=role,
        )
        for workspace, organization_id, role in await authorized_workspaces(db, user)
    ]
