import sqlite3

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from app.models.database import (
    Base,
    ChatSession,
    Message,
    Organization,
    User,
    Workspace,
)


def _sqlite_engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        del connection_record
        if isinstance(dbapi_connection, sqlite3.Connection):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def test_assistant_conversation_schema_contract():
    sessions = Base.metadata.tables["chat_sessions"]
    messages = Base.metadata.tables["messages"]

    assert {
        "id",
        "user_id",
        "workspace_id",
        "title",
        "created_at",
        "updated_at",
        "archived_at",
    }.issubset(sessions.c.keys())

    assert sessions.c.workspace_id.nullable is True
    assert sessions.c.title.nullable is True
    assert sessions.c.archived_at.nullable is True
    assert sessions.c.created_at.nullable is False
    assert sessions.c.updated_at.nullable is False

    workspace_fk = next(iter(sessions.c.workspace_id.foreign_keys))
    assert workspace_fk.target_fullname == "workspaces.id"
    assert workspace_fk.ondelete == "CASCADE"

    assert {
        "id",
        "session_id",
        "role",
        "content",
        "sources_json",
        "created_at",
    }.issubset(messages.c.keys())

    assert messages.c.sources_json.nullable is False
    assert messages.c.created_at.nullable is False

    session_fk = next(iter(messages.c.session_id.foreign_keys))
    assert session_fk.target_fullname == "chat_sessions.id"
    assert session_fk.ondelete == "CASCADE"

    session_indexes = {
        index.name
        for index in sessions.indexes
        if index.name
    }
    message_indexes = {
        index.name
        for index in messages.indexes
        if index.name
    }

    assert "ix_chat_sessions_user_workspace_updated" in session_indexes
    assert "ix_messages_session_id_id" in message_indexes


def test_assistant_conversation_schema_creates_cleanly_on_sqlite():
    engine = _sqlite_engine()

    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())

    assert "chat_sessions" in tables
    assert "messages" in tables

    engine.dispose()


def test_assistant_conversation_defaults_and_workspace_cascade():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(
            email="conversation-test@example.com",
            password_hash="test-only",
        )
        organization = Organization(
            name="Conversation Test",
            slug="conversation-test",
        )
        workspace = Workspace(
            organization=organization,
            name="Engineering",
            slug="engineering",
        )

        db.add_all([user, organization, workspace])
        db.flush()

        session = ChatSession(
            user_id=user.id,
            workspace_id=workspace.id,
            title="Aurora support",
        )
        db.add(session)
        db.flush()

        message = Message(
            session_id=session.id,
            role="user",
            content="Project Aurora destek saatleri nedir?",
        )
        db.add(message)
        db.commit()

        db.refresh(session)
        db.refresh(message)

        session_id = session.id
        message_id = message.id
        workspace_id = workspace.id

        assert session.workspace_id == workspace_id
        assert session.created_at is not None
        assert session.updated_at is not None
        assert session.archived_at is None

        assert message.sources_json == []
        assert message.created_at is not None

        db.delete(workspace)
        db.commit()

        assert db.get(ChatSession, session_id) is None
        assert db.get(Message, message_id) is None

    engine.dispose()
