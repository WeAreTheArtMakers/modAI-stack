import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.deps import websocket_user
from app.services.jobs.redis_queue import RedisIndexQueue
router = APIRouter()
@router.websocket("/ws/indexing")
async def indexing_events(ws: WebSocket):
    await ws.accept()
    try:
        await websocket_user(ws)
        queue = RedisIndexQueue(); pubsub = queue.client.pubsub(); await pubsub.subscribe("modai:indexing:events")
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message": await ws.send_json(json.loads(message["data"]))
        finally:
            await pubsub.unsubscribe("modai:indexing:events"); await pubsub.close(); await queue.close()
    except WebSocketDisconnect: pass
