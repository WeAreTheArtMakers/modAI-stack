import logging
from fastapi import APIRouter, Depends
from app.api.deps import current_user
from app.core.config import get_settings
from app.models.schemas import RagRequest, RagResponse, Source
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import build_rag_prompt
from app.services.rag.embeddings import get_embedding_service
from app.services.qdrant import qdrant_service
router = APIRouter(tags=["rag"])
logger = logging.getLogger(__name__)
@router.post("/rag/query", response_model=RagResponse)
async def query(req: RagRequest, user=Depends(current_user)):
    settings = get_settings()
    query_vector = await get_embedding_service().embed_text(req.question)
    try:
        hits = await qdrant_service.search(
            user_id=int(user["sub"]), vector=query_vector, limit=settings.rag_top_k
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
