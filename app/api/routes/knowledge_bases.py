from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.authorization import authorized_knowledge_bases, require_workspace_role
from app.api.deps import current_user
from app.db.session import get_db
from app.models.database import KnowledgeBase
from app.models.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
from app.services.audit import record_audit_event
router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])
def slugify(value: str) -> str:
    return "-".join(value.lower().split())[:140]
@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    return [
        {
            "id": knowledge_base.id,
            "workspace_id": knowledge_base.workspace_id,
            "name": knowledge_base.name,
            "slug": knowledge_base.slug,
            "description": knowledge_base.description,
            "membership_role": membership.role,
        }
        for knowledge_base, membership in await authorized_knowledge_bases(db, user)
    ]
@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(request: Request, req: KnowledgeBaseCreate, workspace_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await require_workspace_role(db, user, workspace_id, "manager")
    kb = KnowledgeBase(workspace_id=workspace_id, name=req.name, slug=slugify(req.name), description=req.description)
    db.add(kb); await db.flush(); record_audit_event(db, action="knowledge_base_create", resource_type="knowledge_base", actor_user_id=int(user["sub"]), workspace_id=workspace_id, resource_id=kb.id, request=request); await db.commit(); await db.refresh(kb); return kb
