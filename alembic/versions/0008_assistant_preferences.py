"""Add user-scoped Mascot assistant preferences.

Revision ID: 0008_assistant_preferences
Revises: 0007_reconcile_legacy
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_assistant_preferences"
down_revision = "0007_reconcile_legacy"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assistant_name",
            sa.String(length=32),
            nullable=False,
            server_default="modAI",
        ),
        sa.Column(
            "language", sa.String(length=8), nullable=False, server_default="auto"
        ),
        sa.Column(
            "tone",
            sa.String(length=20),
            nullable=False,
            server_default="professional",
        ),
        sa.Column(
            "response_length",
            sa.String(length=12),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", name="uq_assistant_preferences_user_id"
        ),
        sa.CheckConstraint(
            "length(assistant_name) BETWEEN 1 AND 32",
            name="ck_assistant_preferences_name_length",
        ),
        sa.CheckConstraint(
            "language IN ('auto', 'en', 'tr')",
            name="ck_assistant_preferences_language",
        ),
        sa.CheckConstraint(
            "tone IN ('professional', 'friendly', 'technical', 'concise')",
            name="ck_assistant_preferences_tone",
        ),
        sa.CheckConstraint(
            "response_length IN ('short', 'balanced', 'detailed')",
            name="ck_assistant_preferences_response_length",
        ),
    )


def downgrade():
    op.drop_table("assistant_preferences")
