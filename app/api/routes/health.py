import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.services.jobs.redis_queue import RedisIndexQueue
from app.services.llm.ollama import OllamaProvider
from app.services.rag.embeddings import embedding_model_status
router = APIRouter(tags=["health"])
@router.get("/health")
async def health(): return {"status": "ok"}
@router.get("/ready")
async def ready():
    dependencies = {"postgres": False, "redis": False, "qdrant": False}
    try:
        async with engine.connect() as connection: await connection.execute(text("SELECT 1"))
        dependencies["postgres"] = True
    except Exception: pass
    queue = RedisIndexQueue()
    try: dependencies["redis"] = bool(await queue.client.ping())
    except Exception: pass
    finally: await queue.close()
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=3.0) as client:
            dependencies["qdrant"] = (await client.get(f"{get_settings().qdrant_url.rstrip('/')}/healthz")).is_success
    except httpx.HTTPError: pass
    ollama = await OllamaProvider().health_check()
    embedding = embedding_model_status()
    ready = all(dependencies.values())
    return {"status": "ready" if ready else "not_ready", "ready": ready, "dependencies": dependencies, "ollama": {"ready": ollama}, "embedding": embedding}
