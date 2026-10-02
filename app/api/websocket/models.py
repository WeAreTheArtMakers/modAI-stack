import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.deps import ensure_admin, websocket_user
from app.models.schemas import ModelPullRequest
from app.services.models.base import InvalidModelIdentifierError, ModelProviderUnavailableError
from app.services.models.registry import get_model_provider

router = APIRouter()


@router.websocket("/ws/models/pull")
async def pull_model(ws: WebSocket):
    await ws.accept()
    try:
        user = await websocket_user(ws)
        try:
            ensure_admin(user)
        except Exception:
            await ws.send_json({"type": "error", "data": "Admin role required"})
            await ws.close(code=1008)
            return
        try:
            request = ModelPullRequest.model_validate(await ws.receive_json())
            provider = get_model_provider("ollama")
            async for progress in provider.pull_model(request.model):
                await ws.send_json({"type": "model_pull_progress", "model": request.model, **progress})
            await ws.send_json({"type": "complete", "model": request.model})
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
