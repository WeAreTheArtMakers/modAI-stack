import asyncio
from fastapi import APIRouter, Depends
from app.api.deps import current_user
from app.models.schemas import ChatRequest, ChatResponse
from app.services.llm.base import LLMProvider
from app.services.llm.ollama import OllamaProvider
router = APIRouter(tags=["chat"])
provider: LLMProvider = OllamaProvider()
@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user=Depends(current_user)):
    answer = await asyncio.wait_for(provider.generate(req.prompt), timeout=120)
    return ChatResponse(answer=answer)

