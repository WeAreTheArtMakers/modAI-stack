from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import (
    authorized_workspaces,
    require_assistant_conversation_access,
    require_workspace_access,
)
from app.api.deps import current_user
from app.db.session import get_db
from app.models.database import ChatSession, Message
from app.models.schemas import (
    AssistantConversationCreate,
    AssistantConversationDetailResponse,
    AssistantConversationListResponse,
    AssistantConversationResponse,
    AssistantMessageResponse,
    AssistantMessageSource,
)


router = APIRouter(
    prefix="/assistant/conversations",
    tags=["assistant"],
)


def _normalized_title(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@router.post(
    "",
    response_model=AssistantConversationResponse,
    status_code=201,
)
async def create_assistant_conversation(
    req: AssistantConversationCreate,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_workspace_access(
        db,
        user,
        req.workspace_id,
    )

    conversation = ChatSession(
        user_id=int(user["sub"]),
        workspace_id=req.workspace_id,
        title=_normalized_title(req.title),
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get(
    "",
    response_model=AssistantConversationListResponse,
)
async def list_assistant_conversations(
    workspace_id: int | None = Query(default=None, gt=0),
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = int(user["sub"])

    if workspace_id is not None:
        await require_workspace_access(
            db,
            user,
            workspace_id,
        )
        workspace_ids = [workspace_id]
    else:
        workspace_ids = [
            workspace.id
            for workspace, _organization_id, _role
            in await authorized_workspaces(db, user)
        ]

    if not workspace_ids:
        return AssistantConversationListResponse(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    filters = [
        ChatSession.user_id == user_id,
        ChatSession.workspace_id.in_(workspace_ids),
    ]

    if not include_archived:
        filters.append(ChatSession.archived_at.is_(None))

    base_query = select(ChatSession).where(*filters)

    total = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    )

    conversations = list(
        (
            await db.scalars(
                base_query
                .order_by(
                    ChatSession.updated_at.desc(),
                    ChatSession.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )

    return AssistantConversationListResponse(
        items=conversations,
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{conversation_id}",
    response_model=AssistantConversationDetailResponse,
)
async def get_assistant_conversation(
    conversation_id: int,
    message_limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,
    message_offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = (
        await require_assistant_conversation_access(
            db,
            user,
            conversation_id,
        )
    )

    message_total = await db.scalar(
        select(func.count(Message.id)).where(
            Message.session_id == conversation.id
        )
    )

    newest_messages = list(
        (
            await db.scalars(
                select(Message)
                .where(
                    Message.session_id
                    == conversation.id
                )
                .order_by(Message.id.desc())
                .offset(message_offset)
                .limit(message_limit)
            )
        ).all()
    )

    newest_messages.reverse()

    messages = [
        AssistantMessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            sources=[
                AssistantMessageSource.model_validate(
                    source
                )
                for source in (
                    message.sources_json or []
                )
            ],
            created_at=message.created_at,
        )
        for message in newest_messages
    ]

    return AssistantConversationDetailResponse(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        archived_at=conversation.archived_at,
        messages=messages,
        message_total=message_total or 0,
        message_limit=message_limit,
        message_offset=message_offset,
    )


@router.post(
    "/{conversation_id}/archive",
    response_model=AssistantConversationResponse,
)
async def archive_assistant_conversation(
    conversation_id: int,
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = await require_assistant_conversation_access(
        db,
        user,
        conversation_id,
    )

    if conversation.archived_at is None:
        now = datetime.now(timezone.utc)
        conversation.archived_at = now
        conversation.updated_at = now
        await db.commit()
        await db.refresh(conversation)

    return conversation
