import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.db.session import init_db
from app.api.routes import auth, chat, documents, health, knowledge_bases, rag
from app.api.websocket import chat as ws_chat
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(); yield
app = FastAPI(title="Local AI Realtime RAG Platform", lifespan=lifespan)
@app.middleware("http")
async def request_metrics(request: Request, call_next):
    started = time.perf_counter()
    try: response = await call_next(request)
    except Exception: return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-Latency-ms"] = f"{(time.perf_counter()-started)*1000:.1f}"; return response
app.include_router(auth.router); app.include_router(chat.router); app.include_router(documents.router); app.include_router(health.router); app.include_router(knowledge_bases.router); app.include_router(rag.router); app.include_router(ws_chat.router)
