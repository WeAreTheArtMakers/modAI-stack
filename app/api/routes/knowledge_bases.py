from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.authorization import authorized_knowledge_bases, require_workspace_role
from app.api.deps import current_user
from app.db.session import get_db
from app.models.database import KnowledgeBase
from app.models.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])
def slugify(value: str) -> str:
    return "-".join(value.lower().split())[:140]
@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await authorized_knowledge_bases(db, user)
@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(req: KnowledgeBaseCreate, workspace_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    await require_workspace_role(db, user, workspace_id, "manager")
    kb = KnowledgeBase(workspace_id=workspace_id, name=req.name, slug=slugify(req.name), description=req.description)
    db.add(kb); await db.commit(); await db.refresh(kb); return kb
