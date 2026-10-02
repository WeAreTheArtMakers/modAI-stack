import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.deps import ensure_admin, websocket_user
from app.models.schemas import ModelPullRequest
from app.services.models.base import InvalidModelIdentifierError, ModelProviderUnavailableError
from app.services.models.registry import get_model_provider
from app.services.security import RedisRateLimiter
from app.core.config import get_settings
from app.services.observability import metrics
from app.db.session import SessionLocal
from app.services.audit import record_audit_event

router = APIRouter()


@router.websocket("/ws/models/pull")
async def pull_model(ws: WebSocket):
    await ws.accept()
    try:
        user = await websocket_user(ws, "models_pull")
        try:
            ensure_admin(user)
        except Exception:
            await ws.send_json({"type": "error", "data": "Admin role required"})
            await ws.close(code=1008)
            return
        limiter = RedisRateLimiter()
        try: await limiter.enforce("model-pull", str(user["sub"]), get_settings().rate_limit_model_pull_per_hour, 3600)
        finally: await limiter.close()
        try:
            request = ModelPullRequest.model_validate(await ws.receive_json())
            async with SessionLocal() as db:
                record_audit_event(db, action="model_pull_initiated", resource_type="model", actor_user_id=int(user["sub"]), resource_id=request.model, metadata={"provider": "ollama"})
                await db.commit()
            provider = get_model_provider("ollama")
            async for progress in provider.pull_model(request.model):
                await ws.send_json({"type": "model_pull_progress", "model": request.model, **progress})
            await ws.send_json({"type": "complete", "model": request.model})
            async with SessionLocal() as db:
                record_audit_event(db, action="model_pull_completed", resource_type="model", actor_user_id=int(user["sub"]), resource_id=request.model, metadata={"provider": "ollama"})
                await db.commit()
            metrics.event("model_pull")
        except (ValidationError, InvalidModelIdentifierError):
            await ws.send_json({"type": "error", "data": "Invalid model identifier"})
        except ModelProviderUnavailableError:
            await ws.send_json({"type": "error", "data": "Model provider is unavailable"})
        except Exception:
            await ws.send_json({"type": "error", "data": "Model pull could not be completed"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
