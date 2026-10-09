import asyncio
from time import perf_counter

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


async def _fixed(text: str):
    yield text


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

            timings: dict[str, float] = {}
            async with SessionLocal() as db:
                try:
                    started = perf_counter()
                    authorized_kb_ids, kb_scope = (
                        await resolve_knowledge_base_scope(
                            db,
                            user,
                            req.knowledge_base_ids,
                        )
                    )
                    workspace_id = int(kb_scope[1].id)
                    organization_id = int(
                        kb_scope[1].organization_id
                    )
                    del kb_scope

                    history = None
                    if req.conversation_id is not None:
                        history = await load_conversation_history(
                            db,
                            user,
                            req.conversation_id,
                            workspace_id,
                        )

                    preferences = await get_effective_assistant_preferences(
                        db, int(user["sub"])
                    )
                    timings["authorization_ms"] = (perf_counter() - started) * 1000

                    generation_preferences = generation_preference_values(preferences)
                    if req.response_language is not None:
                        # Request-scoped presentation override; the stored preference is untouched.
                        generation_preferences["language"] = req.response_language

                    context = await retrieve_rag_context(
                        req.question,
                        db=db,
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        knowledge_base_ids=authorized_kb_ids,
                        history=history,
                        preferences=generation_preferences,
                        response_language=req.response_language,
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

            sources_event: dict = {
                "type": "sources",
                "data": [
                    source.model_dump(mode="json")
                    for source in context.sources
                ],
            }
            if req.diagnostics:
                for name in ("embedding", "retrieval", "liveness", "prompt"):
                    value = getattr(context, f"{name}_latency_ms", None)
                    if isinstance(value, (int, float)):
                        timings[f"{name}_ms"] = value
                timings["prompt_chars"] = len(context.prompt)
                sources_event["timings"] = {key: round(value, 1) for key, value in timings.items()}
            await ws.send_json(sources_event)

            answer_parts: list[str] = []
            generation_stats: dict = {}
            generation_started = perf_counter()
            first_token_ms: float | None = None

            try:
                if context.table_conflict_answer is not None:
                    # The retrieved tables conflict for the number asked: no model answer.
                    stream = _fixed(context.table_conflict_answer)
                elif req.diagnostics:
                    stream = provider.stream(context.prompt, stats=generation_stats)
                else:
                    stream = provider.stream(context.prompt)
                async for token in stream:
                    if first_token_ms is None:
                        first_token_ms = (perf_counter() - generation_started) * 1000
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
                            workspace_id=workspace_id,
                            question=req.question,
                            answer="".join(answer_parts),
                            sources=context.sources,
                        )

                complete_event: dict = {"type": "complete"}
                if req.diagnostics:
                    complete_event["timings"] = {
                        "first_token_ms": round(first_token_ms, 1) if first_token_ms is not None else None,
                        "generation_ms": round((perf_counter() - generation_started) * 1000, 1),
                        **generation_stats,
                    }
                await ws.send_json(complete_event)

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
