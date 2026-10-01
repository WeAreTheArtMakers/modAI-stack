from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.db.session import get_db
from app.models.database import KnowledgeBase, Membership, Workspace
from app.models.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse
router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])
def slugify(value: str) -> str:
    return "-".join(value.lower().split())[:140]
@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(KnowledgeBase).join(Workspace).join(Membership, Membership.workspace_id == Workspace.id).where(Membership.user_id == int(user["sub"]))
    return list((await db.scalars(stmt.order_by(KnowledgeBase.id))).all())
@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(req: KnowledgeBaseCreate, workspace_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    membership = await db.scalar(select(Membership).where(Membership.user_id == int(user["sub"]), Membership.workspace_id == workspace_id))
    if not membership or membership.role not in {"admin", "manager"}: from fastapi import HTTPException; raise HTTPException(403, "Insufficient workspace permissions")
    kb = KnowledgeBase(workspace_id=workspace_id, name=req.name, slug=slugify(req.name), description=req.description)
    db.add(kb); await db.commit(); await db.refresh(kb); return kb
