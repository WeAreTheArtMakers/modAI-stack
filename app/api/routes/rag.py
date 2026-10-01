import logging
from fastapi import APIRouter, Depends
from app.api.deps import current_user
from app.core.config import get_settings
from app.models.schemas import RagRequest, RagResponse, Source
from app.models.database import KnowledgeBase, Membership, Workspace
from app.db.session import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import build_rag_prompt
from app.services.rag.embeddings import get_embedding_service
from app.services.qdrant import qdrant_service
router = APIRouter(tags=["rag"])
logger = logging.getLogger(__name__)
@router.post("/rag/query", response_model=RagResponse)
async def query(req: RagRequest, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    query_vector = await get_embedding_service().embed_text(req.question)
    kb_scope = None
    authorized_kb_ids: list[int] = []
    if req.knowledge_base_ids:
        stmt = select(KnowledgeBase, Workspace).join(Workspace).join(Membership, Membership.workspace_id == Workspace.id).where(Membership.user_id == int(user["sub"]), KnowledgeBase.id.in_(req.knowledge_base_ids))
        rows = (await db.execute(stmt)).all()
        authorized_kb_ids = [row[0].id for row in rows]
        if len(authorized_kb_ids) != len(set(req.knowledge_base_ids)):
            from fastapi import HTTPException
            raise HTTPException(403, "Knowledge base access required")
        scopes = {(row[1].organization_id, row[1].id) for row in rows}
        if len(scopes) != 1:
            from fastapi import HTTPException
            raise HTTPException(400, "Selected knowledge bases must share a workspace")
        kb_scope = rows[0]
    try:
        hits = await qdrant_service.search(
            user_id=int(user["sub"]), vector=query_vector, limit=settings.rag_top_k,
            organization_id=kb_scope[1].organization_id if kb_scope else None,
            workspace_id=kb_scope[1].id if kb_scope else None,
            knowledge_base_ids=authorized_kb_ids or None,
        )
    except Exception:
        logger.exception("RAG vector search failed", extra={"user_id": int(user["sub"])})
        hits = []
    chunks = [hit.payload["text"] for hit in hits if hit.payload and hit.payload.get("text")]
    prompt = build_rag_prompt(req.question, chunks)
    sources = [
        Source(
            document=hit.payload.get("filename", "unknown"), score=hit.score,
            document_id=hit.payload.get("document_id"),
            chunk_index=hit.payload.get("chunk_index"), text=hit.payload.get("text"),
        )
        for hit in hits if hit.payload
    ]
    return RagResponse(answer=await OllamaProvider().generate(prompt), sources=sources)
