from fastapi import APIRouter
from app.services.llm.ollama import OllamaProvider
router = APIRouter(tags=["health"])
@router.get("/health")
async def health(): return {"status": "ok"}
@router.get("/ready")
async def ready(): return {"status": "ready", "ollama": await OllamaProvider().health_check()}

