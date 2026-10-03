import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import init_db
from app.api.routes import admin, audit, auth, chat, documents, health, knowledge_bases, metrics, models, rag, retrieval, workspaces
from app.api.websocket import chat as ws_chat
from app.api.websocket import indexing as ws_indexing
from app.api.websocket import rag as ws_rag
from app.api.websocket import models as ws_models
from app.services.observability import JsonFormatter, metrics as app_metrics, request_id_context

logger = logging.getLogger(__name__)
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def validate_production_config() -> None:
    settings = get_settings()
    placeholder = settings.jwt_secret.lower() in {"change-me-in-production", "replace-with-a-long-random-secret", "ci-only-secret"}
    if settings.app_env == "production" and placeholder:
        raise RuntimeError("JWT_SECRET must be a non-placeholder secret in production")
    if settings.app_env == "production" and not settings.refresh_cookie_secure:
        raise RuntimeError("REFRESH_COOKIE_SECURE must be enabled in production")


def configure_logging() -> None:
    if get_settings().app_env != "production":
        return
    root = logging.getLogger()
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]
        root.setLevel(logging.INFO)
@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_config()
    configure_logging()
    await init_db(); yield
app = FastAPI(title="Local AI Realtime RAG Platform", lifespan=lifespan)
@app.middleware("http")
async def request_metrics(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    request_id = request_id if REQUEST_ID.fullmatch(request_id) else uuid.uuid4().hex
    request.state.request_id = request_id
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        try: response = await call_next(request)
        except Exception:
            logger.exception("Unhandled HTTP error", extra={"component": "api"})
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        duration = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", request.url.path)
        app_metrics.request(request.method, route, response.status_code, duration)
        logger.info("HTTP request completed", extra={"component": "api", "status_code": response.status_code, "duration_ms": round(duration * 1000, 1), "user_id": getattr(request.state, "user_id", None), "workspace_id": request.query_params.get("workspace_id")})
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Request-Latency-ms"] = f"{duration*1000:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'self'"
        return response
    finally:
        request_id_context.reset(token)
app.include_router(auth.router); app.include_router(chat.router); app.include_router(documents.router); app.include_router(health.router); app.include_router(knowledge_bases.router); app.include_router(workspaces.router); app.include_router(models.router); app.include_router(rag.router); app.include_router(retrieval.router); app.include_router(audit.router); app.include_router(admin.router); app.include_router(metrics.router); app.include_router(ws_chat.router); app.include_router(ws_indexing.router); app.include_router(ws_rag.router); app.include_router(ws_models.router)
