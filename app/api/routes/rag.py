from fastapi import APIRouter, Depends
from app.api.deps import current_user
from app.models.schemas import RagRequest, RagResponse
from app.api.authorization import resolve_knowledge_base_scope
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import retrieve_rag_context
router = APIRouter(tags=["rag"])
@router.post("/rag/query", response_model=RagResponse)
async def query(req: RagRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    authorized_kb_ids, kb_scope = await resolve_knowledge_base_scope(db, user, req.knowledge_base_ids)
    context = await retrieve_rag_context(
        req.question,
        user_id=int(user["sub"]),
        organization_id=kb_scope[1].organization_id if kb_scope else None,
        workspace_id=kb_scope[1].id if kb_scope else None,
        knowledge_base_ids=authorized_kb_ids or None,
    )
    return RagResponse(answer=await OllamaProvider().generate(context.prompt), sources=context.sources)
