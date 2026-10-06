from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.deps import current_user
from app.models.schemas import RagRequest, RagResponse
from app.api.authorization import resolve_knowledge_base_scope
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import retrieve_rag_context
from app.services.rag.embeddings import EmbeddingModelUnavailableError, embedding_model_unavailable_detail
from app.services.security import RedisRateLimiter
from app.core.config import get_settings
from app.services.observability import metrics
from app.services.assistant_conversations import (
    persist_completed_turn,
    require_conversation_turn_scope,
)
router = APIRouter(tags=["rag"])
@router.post("/rag/query", response_model=RagResponse)
async def query(req: RagRequest, request: Request, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    limiter = RedisRateLimiter()
    try: await limiter.enforce("rag", str(user["sub"]), get_settings().rate_limit_rag_per_minute, 60)
    finally: await limiter.close()
    authorized_kb_ids, kb_scope = await resolve_knowledge_base_scope(db, user, req.knowledge_base_ids)

    if req.conversation_id is not None:
        await require_conversation_turn_scope(
            db,
            user,
            req.conversation_id,
            kb_scope[1].id,
        )

    try:
        context = await retrieve_rag_context(
            req.question,
            db=db,
            organization_id=kb_scope[1].organization_id,
            workspace_id=kb_scope[1].id,
            knowledge_base_ids=authorized_kb_ids,
        )
    except EmbeddingModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=embedding_model_unavailable_detail()) from exc
    metrics.event("rag_requests")

    answer = await OllamaProvider().generate(context.prompt)

    if req.conversation_id is not None:
        await persist_completed_turn(
            db,
            user,
            conversation_id=req.conversation_id,
            workspace_id=kb_scope[1].id,
            question=req.question,
            answer=answer,
            sources=context.sources,
        )

    return RagResponse(
        answer=answer,
        sources=context.sources,
    )
