import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.authorization import resolve_knowledge_base_scope
from app.api.deps import websocket_user
from app.db.session import SessionLocal
from app.models.schemas import RagRequest
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import retrieve_rag_context
from app.services.rag.embeddings import EmbeddingModelUnavailableError, embedding_model_unavailable_detail

router = APIRouter()
provider = OllamaProvider()


@router.websocket("/ws/rag")
async def websocket_rag(ws: WebSocket):
    await ws.accept()
    try:
        user = await websocket_user(ws)
        while True:
            try:
                req = RagRequest.model_validate(await ws.receive_json())
            except ValidationError:
                await ws.send_json({"type": "error", "data": "Invalid RAG request"})
                continue

            async with SessionLocal() as db:
                try:
                    authorized_kb_ids, kb_scope = await resolve_knowledge_base_scope(
                        db, user, req.knowledge_base_ids
                    )
                    context = await retrieve_rag_context(
                        req.question,
                        user_id=int(user["sub"]),
                        organization_id=kb_scope[1].organization_id if kb_scope else None,
                        workspace_id=kb_scope[1].id if kb_scope else None,
                        knowledge_base_ids=authorized_kb_ids or None,
                    )
                except EmbeddingModelUnavailableError:
                    await ws.send_json({"type": "error", "data": embedding_model_unavailable_detail()})
                    continue
                except Exception:
                    await ws.send_json({"type": "error", "data": "RAG request failed"})
                    continue

            await ws.send_json({
                "type": "sources",
                "data": [source.model_dump(mode="json") for source in context.sources],
            })
            try:
                async for token in provider.stream(context.prompt):
                    await ws.send_json({"type": "token", "data": token})
                await ws.send_json({"type": "complete"})
            except Exception:
                await ws.send_json({"type": "error", "data": "RAG streaming failed"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        try:
            await ws.close(code=1008)
        except Exception:
            pass
