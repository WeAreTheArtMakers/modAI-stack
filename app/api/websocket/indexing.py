import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.authorization import require_workspace_access
from app.api.deps import websocket_user
from app.db.session import SessionLocal
from app.services.jobs.redis_queue import RedisIndexQueue
router = APIRouter()
@router.websocket("/ws/indexing")
async def indexing_events(ws: WebSocket):
    await ws.accept()
    try:
        user = await websocket_user(ws)
        raw_workspace_id = ws.query_params.get("workspace_id")
        try:
            workspace_id = int(raw_workspace_id or "")
        except ValueError:
            await ws.close(code=1008)
            return
        async with SessionLocal() as db:
            await require_workspace_access(db, user, workspace_id)

        queue = RedisIndexQueue(); pubsub = queue.client.pubsub()
        channel = queue.events_channel(workspace_id)
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message": await ws.send_json(json.loads(message["data"]))
        finally:
            await pubsub.unsubscribe(channel); await pubsub.close(); await queue.close()
    except WebSocketDisconnect: pass
    except Exception:
        try: await ws.close(code=1008)
        except Exception: pass
