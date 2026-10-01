from fastapi import APIRouter, Depends
from app.api.deps import current_user
from app.models.schemas import RagRequest, RagResponse
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import build_rag_prompt
router = APIRouter(tags=["rag"])
@router.post("/rag/query", response_model=RagResponse)
async def query(req: RagRequest, user=Depends(current_user)):
    # Qdrant search is intentionally isolated behind QdrantService; wire embeddings here in deployment.
    prompt = build_rag_prompt(req.question, [])
    return RagResponse(answer=await OllamaProvider().generate(prompt), sources=[])
