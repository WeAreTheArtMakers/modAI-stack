import os

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.api.routes import assistant_conversations
from app.models.database import (
    Base,
    ChatSession,
    Membership,
    Organization,
    User,
    Workspace,
)
from app.models.schemas import AssistantConversationCreate


@pytest_asyncio.fixture
async def conversation_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with maker() as db:
        organization = Organization(
            name="Conversation Organization",
            slug="conversation-organization",
        )
        workspace_a = Workspace(
            name="Engineering",
            slug="engineering",
            organization=organization,
        )
        workspace_b = Workspace(
            name="Finance",
            slug="finance",
            organization=organization,
        )

        owner = User(
            email="conversation-owner@example.com",
            password_hash="x",
        )
        other = User(
            email="conversation-other@example.com",
            password_hash="x",
        )

        db.add_all(
            [
                organization,
                workspace_a,
                workspace_b,
                owner,
                other,
            ]
        )
        await db.flush()

        owner_membership = Membership(
            user_id=owner.id,
            organization_id=organization.id,
            workspace_id=workspace_a.id,
            role="user",
        )
        other_membership = Membership(
            user_id=other.id,
            organization_id=organization.id,
            workspace_id=workspace_a.id,
            role="user",
        )

        db.add_all(
            [
                owner_membership,
                other_membership,
            ]
        )
        await db.commit()

        yield db, {
            "owner": {
                "sub": str(owner.id),
                "role": "user",
            },
            "other": {
                "sub": str(other.id),
                "role": "user",
            },
            "owner_id": owner.id,
            "other_id": other.id,
            "workspace_a": workspace_a.id,
            "workspace_b": workspace_b.id,
            "owner_membership_id": owner_membership.id,
        }

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_requires_current_workspace_access_and_normalizes_title(
    conversation_session,
):
    db, ids = conversation_session

    created = await assistant_conversations.create_assistant_conversation(
        AssistantConversationCreate(
            workspace_id=ids["workspace_a"],
            title="  Aurora support  ",
        ),
        user=ids["owner"],
        db=db,
    )

    assert created.user_id == ids["owner_id"]
    assert created.workspace_id == ids["workspace_a"]
    assert created.title == "Aurora support"
    assert created.created_at is not None
    assert created.updated_at is not None
    assert created.archived_at is None

    with pytest.raises(HTTPException) as error:
        await assistant_conversations.create_assistant_conversation(
            AssistantConversationCreate(
                workspace_id=ids["workspace_b"],
                title="Forbidden",
            ),
            user=ids["owner"],
            db=db,
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_list_is_owner_scoped_current_access_scoped_and_paginated(
    conversation_session,
):
    db, ids = conversation_session

    for title in ("One", "Two", "Three"):
        await assistant_conversations.create_assistant_conversation(
            AssistantConversationCreate(
                workspace_id=ids["workspace_a"],
                title=title,
            ),
            user=ids["owner"],
            db=db,
        )

    await assistant_conversations.create_assistant_conversation(
        AssistantConversationCreate(
            workspace_id=ids["workspace_a"],
            title="Other user",
        ),
        user=ids["other"],
        db=db,
    )

    legacy = ChatSession(
        user_id=ids["owner_id"],
        workspace_id=None,
        title="Legacy",
    )
    db.add(legacy)
    await db.commit()

    result = await assistant_conversations.list_assistant_conversations(
        workspace_id=None,
        include_archived=False,
        limit=2,
        offset=1,
        user=ids["owner"],
        db=db,
    )

    assert result.total == 3
    assert result.limit == 2
    assert result.offset == 1
    assert len(result.items) == 2
    assert all(
        item.workspace_id == ids["workspace_a"]
        for item in result.items
    )


@pytest.mark.asyncio
async def test_other_users_conversation_is_hidden_as_not_found(
    conversation_session,
):
    db, ids = conversation_session

    conversation = await assistant_conversations.create_assistant_conversation(
        AssistantConversationCreate(
            workspace_id=ids["workspace_a"],
            title="Private",
        ),
        user=ids["owner"],
        db=db,
    )

    with pytest.raises(HTTPException) as error:
        await assistant_conversations.get_assistant_conversation(
            conversation.id,
            user=ids["other"],
            db=db,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_owner_loses_access_to_existing_conversation(
    conversation_session,
):
    db, ids = conversation_session

    conversation = await assistant_conversations.create_assistant_conversation(
        AssistantConversationCreate(
            workspace_id=ids["workspace_a"],
            title="Access will be revoked",
        ),
        user=ids["owner"],
        db=db,
    )

    membership = await db.get(
        Membership,
        ids["owner_membership_id"],
    )
    await db.delete(membership)
    await db.commit()

    with pytest.raises(HTTPException) as error:
        await assistant_conversations.get_assistant_conversation(
            conversation.id,
            user=ids["owner"],
            db=db,
        )

    assert error.value.status_code == 403

    result = await assistant_conversations.list_assistant_conversations(
        workspace_id=None,
        include_archived=False,
        limit=50,
        offset=0,
        user=ids["owner"],
        db=db,
    )

    assert result.total == 0
    assert result.items == []


@pytest.mark.asyncio
async def test_archive_is_idempotent_and_hidden_from_default_list(
    conversation_session,
):
    db, ids = conversation_session

    conversation = await assistant_conversations.create_assistant_conversation(
        AssistantConversationCreate(
            workspace_id=ids["workspace_a"],
            title="Archive me",
        ),
        user=ids["owner"],
        db=db,
    )

    archived = await assistant_conversations.archive_assistant_conversation(
        conversation.id,
        user=ids["owner"],
        db=db,
    )
    first_archived_at = archived.archived_at

    archived_again = (
        await assistant_conversations.archive_assistant_conversation(
            conversation.id,
            user=ids["owner"],
            db=db,
        )
    )

    assert first_archived_at is not None
    assert archived_again.archived_at == first_archived_at

    active = await assistant_conversations.list_assistant_conversations(
        workspace_id=ids["workspace_a"],
        include_archived=False,
        limit=50,
        offset=0,
        user=ids["owner"],
        db=db,
    )
    assert active.total == 0

    all_items = await assistant_conversations.list_assistant_conversations(
        workspace_id=ids["workspace_a"],
        include_archived=True,
        limit=50,
        offset=0,
        user=ids["owner"],
        db=db,
    )
    assert all_items.total == 1
    assert all_items.items[0].id == conversation.id


@pytest.mark.asyncio
async def test_legacy_null_workspace_session_is_not_exposed(
    conversation_session,
):
    db, ids = conversation_session

    legacy = ChatSession(
        user_id=ids["owner_id"],
        workspace_id=None,
        title="Legacy session",
    )
    db.add(legacy)
    await db.commit()
    await db.refresh(legacy)

    with pytest.raises(HTTPException) as error:
        await assistant_conversations.get_assistant_conversation(
            legacy.id,
            user=ids["owner"],
            db=db,
        )

    assert error.value.status_code == 404

    rows = list(
        (
            await db.scalars(
                select(ChatSession).where(
                    ChatSession.user_id == ids["owner_id"]
                )
            )
        ).all()
    )
    assert legacy in rows
