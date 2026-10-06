"""Extend legacy chat storage for persistent assistant conversations."""

from alembic import op
import sqlalchemy as sa


revision = "0006_assistant_conversations"
down_revision = "0005_retrieval_generation_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chat_sessions",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "title",
            sa.String(200),
            nullable=True,
        ),
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "chat_sessions",
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_chat_sessions_user_workspace_updated",
        "chat_sessions",
        ["user_id", "workspace_id", "updated_at"],
        unique=False,
    )

    op.add_column(
        "messages",
        sa.Column(
            "sources_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_messages_session_id_id",
        "messages",
        ["session_id", "id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_messages_session_id_id",
        table_name="messages",
    )
    op.drop_column("messages", "created_at")
    op.drop_column("messages", "sources_json")

    op.drop_index(
        "ix_chat_sessions_user_workspace_updated",
        table_name="chat_sessions",
    )
    op.drop_column("chat_sessions", "archived_at")
    op.drop_column("chat_sessions", "updated_at")
    op.drop_column("chat_sessions", "created_at")
    op.drop_column("chat_sessions", "title")
    op.drop_column("chat_sessions", "workspace_id")
