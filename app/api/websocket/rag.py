import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.authorization import resolve_knowledge_base_scope
from app.api.deps import websocket_user
from app.db.session import SessionLocal
from app.models.schemas import RagRequest
from app.services.assistant_conversations import (
    load_conversation_history,
    persist_completed_turn,
)
from app.services.assistant_preferences import (
    generation_preference_values,
    get_effective_assistant_preferences,
)
from app.services.llm.ollama import OllamaProvider
from app.services.rag.pipeline import retrieve_rag_context
from app.services.rag.embeddings import (
    EmbeddingModelUnavailableError,
    embedding_model_unavailable_detail,
)


router = APIRouter()
provider = OllamaProvider()


@router.websocket("/ws/rag")
async def websocket_rag(ws: WebSocket):
    await ws.accept()

    try:
        user = await websocket_user(ws, "rag")

        while True:
            try:
                req = RagRequest.model_validate(
                    await ws.receive_json()
                )
            except ValidationError:
                await ws.send_json(
                    {
                        "type": "error",
                        "data": "Invalid RAG request",
                    }
                )
                continue

            async with SessionLocal() as db:
                try:
                    authorized_kb_ids, kb_scope = (
                        await resolve_knowledge_base_scope(
                            db,
                            user,
                            req.knowledge_base_ids,
                        )
                    )

                    history = None
                    if req.conversation_id is not None:
                        history = await load_conversation_history(
                            db,
                            user,
                            req.conversation_id,
                            kb_scope[1].id,
                        )

                    preferences = await get_effective_assistant_preferences(
                        db, int(user["sub"])
                    )

                    context = await retrieve_rag_context(
                        req.question,
                        db=db,
                        organization_id=(
                            kb_scope[1].organization_id
                        ),
                        workspace_id=kb_scope[1].id,
                        knowledge_base_ids=authorized_kb_ids,
                        history=history,
                        preferences=generation_preference_values(preferences),
                    )
                except EmbeddingModelUnavailableError:
                    await ws.send_json(
                        {
                            "type": "error",
                            "data": (
                                embedding_model_unavailable_detail()
                            ),
                        }
                    )
                    continue
                except Exception:
                    await ws.send_json(
                        {
                            "type": "error",
                            "data": "RAG request failed",
                        }
                    )
                    continue

            await ws.send_json(
                {
                    "type": "sources",
                    "data": [
                        source.model_dump(mode="json")
                        for source in context.sources
                    ],
                }
            )

            answer_parts: list[str] = []

            try:
                async for token in provider.stream(
                    context.prompt
                ):
                    await ws.send_json(
                        {
                            "type": "token",
                            "data": token,
                        }
                    )
                    answer_parts.append(token)

                if req.conversation_id is not None:
                    async with SessionLocal() as db:
                        await persist_completed_turn(
                            db,
                            user,
                            conversation_id=(
                                req.conversation_id
                            ),
                            workspace_id=kb_scope[1].id,
                            question=req.question,
                            answer="".join(answer_parts),
                            sources=context.sources,
                        )

                await ws.send_json(
                    {
                        "type": "complete",
                    }
                )

            except (
                WebSocketDisconnect,
                asyncio.CancelledError,
            ):
                raise
            except Exception:
                try:
                    await ws.send_json(
                        {
                            "type": "error",
                            "data": "RAG streaming failed",
                        }
                    )
                except (
                    WebSocketDisconnect,
                    asyncio.CancelledError,
                ):
                    raise

    except (
        WebSocketDisconnect,
        asyncio.CancelledError,
    ):
        pass
    except Exception:
        try:
            await ws.close(code=1008)
        except Exception:
            pass
