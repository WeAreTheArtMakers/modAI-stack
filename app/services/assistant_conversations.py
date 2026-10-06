from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_assistant_conversation_access
from app.models.database import ChatSession, Message
from app.models.schemas import Source


async def require_conversation_turn_scope(
    db: AsyncSession,
    user: dict,
    conversation_id: int,
    workspace_id: int,
) -> ChatSession:
    conversation = await require_assistant_conversation_access(
        db,
        user,
        conversation_id,
    )

    if conversation.workspace_id != workspace_id:
        raise HTTPException(
            400,
            "Conversation and selected knowledge bases must share a workspace",
        )

    if conversation.archived_at is not None:
        raise HTTPException(
            409,
            "Conversation is archived",
        )

    return conversation


def compact_source_snapshot(
    sources: list[Source],
) -> list[dict]:
    return [
        {
            "document": source.document,
            "document_id": source.document_id,
            "chunk_index": source.chunk_index,
            "score": source.score,
        }
        for source in sources
    ]


async def persist_completed_turn(
    db: AsyncSession,
    user: dict,
    *,
    conversation_id: int,
    workspace_id: int,
    question: str,
    answer: str,
    sources: list[Source],
) -> None:
    conversation = await require_conversation_turn_scope(
        db,
        user,
        conversation_id,
        workspace_id,
    )

    now = datetime.now(timezone.utc)

    db.add_all(
        [
            Message(
                session_id=conversation.id,
                role="user",
                content=question,
                sources_json=[],
            ),
            Message(
                session_id=conversation.id,
                role="assistant",
                content=answer,
                sources_json=compact_source_snapshot(sources),
            ),
        ]
    )

    conversation.updated_at = now

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
