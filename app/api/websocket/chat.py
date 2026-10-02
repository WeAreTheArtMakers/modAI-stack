import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.deps import websocket_user
from app.api.routes.chat import provider
router = APIRouter()
@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await ws.accept()
    try:
        await websocket_user(ws, "chat")
        while True:
            prompt = await ws.receive_text()
            async for token in provider.stream(prompt): await ws.send_json({"type": "token", "data": token})
            await ws.send_json({"type": "complete"})
    except (WebSocketDisconnect, asyncio.CancelledError): pass
    except Exception:
        try: await ws.send_json({"type": "error", "data": "streaming failed"})
        except Exception: pass
