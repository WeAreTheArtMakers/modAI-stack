"""Add an archive marker for obsolete documents.

Revision ID: 0009_document_archive
Revises: 0008_assistant_preferences
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_document_archive"
down_revision = "0008_assistant_preferences"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable with no default: every existing document stays live and
    # retrievable. Only an explicit archive action sets the timestamp.
    op.add_column(
        "documents",
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_documents_archived_at",
        "documents",
        ["archived_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_documents_archived_at",
        table_name="documents",
    )
    op.drop_column("documents", "archived_at")
