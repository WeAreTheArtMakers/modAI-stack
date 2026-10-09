import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.deps import current_user
from app.models.schemas import RagRequest, RagResponse
from app.api.authorization import resolve_knowledge_base_scope
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import retrieve_rag_context
from app.services.rag.embeddings import EmbeddingModelUnavailableError, embedding_model_unavailable_detail, get_embedding_service
from app.services.security import RedisRateLimiter
from app.core.config import get_settings
from app.services.observability import metrics
from app.services.assistant_conversations import (
    load_conversation_history,
    persist_completed_turn,
)
from app.services.assistant_preferences import (
    generation_preference_values,
    get_effective_assistant_preferences,
)
logger = logging.getLogger(__name__)
router = APIRouter(tags=["rag"])

WARMUP_INTERVAL_SECONDS = 60
_warmup = {"last": float("-inf"), "task": None}


@router.post("/rag/warmup", status_code=202)
async def warm_up_generation_model(user=Depends(current_user)):
    """Load the generation model (Ollama) and this process's embedding model before the user's
    next question, so neither load is paid inside it.

    Authenticated, at most one load request per minute per API process and never while the
    previous one is still loading (a cold load can outlast the interval); Ollama's own
    keep-alive and memory settings are unchanged. Returns immediately.
    """
    del user
    now = time.monotonic()
    running = _warmup["task"] is not None and not _warmup["task"].done()
    if running or now - _warmup["last"] < WARMUP_INTERVAL_SECONDS:
        return {"status": "recent"}
    _warmup["last"] = now

    async def load() -> None:
        provider = OllamaProvider()
        # One after the other: loading both at once (torch in this process, 3+ GB in Ollama) was
        # measured several times slower on a 16 GB machine. The embedding model loads once per
        # process and is kept, so after the first warm-up this step returns at once.
        try:
            await get_embedding_service().embed_text("ısınma")
        except Exception:
            logger.warning("Embedding model warm-up failed", extra={"component": "rag"})
        try:
            await provider.preload()
        except Exception:
            logger.warning("Generation model warm-up failed", extra={"component": "rag"})
        finally:
            await provider.client.aclose()

    _warmup["task"] = asyncio.create_task(load())
    return {"status": "warming"}
@router.post("/rag/query", response_model=RagResponse)
async def query(req: RagRequest, request: Request, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    limiter = RedisRateLimiter()
    try: await limiter.enforce("rag", str(user["sub"]), get_settings().rate_limit_rag_per_minute, 60)
    finally: await limiter.close()
    authorized_kb_ids, kb_scope = await resolve_knowledge_base_scope(db, user, req.knowledge_base_ids)
    workspace_id = int(kb_scope[1].id)
    organization_id = int(kb_scope[1].organization_id)

    history = None
    if req.conversation_id is not None:
        history = await load_conversation_history(
            db,
            user,
            req.conversation_id,
            workspace_id,
        )

    preferences = await get_effective_assistant_preferences(
        db, int(user["sub"])
    )
    generation_preferences = generation_preference_values(preferences)
    if req.response_language is not None:
        generation_preferences["language"] = req.response_language
    if req.response_length is not None:
        generation_preferences["response_length"] = req.response_length

    try:
        context = await retrieve_rag_context(
            req.question,
            db=db,
            organization_id=organization_id,
            workspace_id=workspace_id,
            knowledge_base_ids=authorized_kb_ids,
            history=history,
            preferences=generation_preferences,
            response_language=req.response_language,
        )
    except EmbeddingModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=embedding_model_unavailable_detail()) from exc
    metrics.event("rag_requests")

    # Retrieval, authorization, and preference reads are complete. Do not keep
    # their transaction open while waiting for model generation.
    await db.rollback()

    if context.table_conflict_answer is not None:
        answer = context.table_conflict_answer  # retrieved tables conflict for the number asked
    else:
        answer = await OllamaProvider().generate(context.prompt)

    if req.conversation_id is not None:
        await persist_completed_turn(
            db,
            user,
            conversation_id=req.conversation_id,
            workspace_id=workspace_id,
            question=req.question,
            answer=answer,
            sources=context.sources,
        )

    return RagResponse(
        answer=answer,
        sources=context.sources,
    )
