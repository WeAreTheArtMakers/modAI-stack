"""Reconcile legacy columns and indexes with current ORM contracts.

Revision ID: 0007_reconcile_legacy
Revises: 0006_assistant_conversations
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_reconcile_legacy"
down_revision = "0006_assistant_conversations"
branch_labels = None
depends_on = None


REQUIRED_TIMESTAMP_COLUMNS = (
    ("users", "created_at"),
    ("organizations", "created_at"),
    ("documents", "created_at"),
    ("document_versions", "created_at"),
    ("index_jobs", "created_at"),
    ("index_jobs", "updated_at"),
)

INDEXES = (
    ("ix_documents_content_hash", "documents", ["content_hash"]),
    ("ix_documents_knowledge_base_id", "documents", ["knowledge_base_id"]),
    ("ix_documents_organization_id", "documents", ["organization_id"]),
    ("ix_documents_workspace_id", "documents", ["workspace_id"]),
    ("ix_document_versions_content_hash", "document_versions", ["content_hash"]),
    ("ix_knowledge_bases_workspace_id", "knowledge_bases", ["workspace_id"]),
    ("ix_memberships_organization_id", "memberships", ["organization_id"]),
    ("ix_memberships_workspace_id", "memberships", ["workspace_id"]),
)

# These constraints duplicate the explicitly created unique indexes from
# migrations 0001 and 0003. The model declares the unique indexes; removing
# only the redundant constraint-backed indexes preserves uniqueness.
DUPLICATE_UNIQUE_CONSTRAINTS = (
    ("users", "users_email_key", ["email"]),
    ("invitations", "invitations_token_hash_key", ["token_hash"]),
)


def upgrade():
    bind = op.get_bind()

    null_columns = [
        f"{table}.{column}"
        for table, column in REQUIRED_TIMESTAMP_COLUMNS
        if bind.execute(
            sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table}" WHERE "{column}" IS NULL)')
        ).scalar()
    ]
    if null_columns:
        raise RuntimeError(
            "Cannot enforce required timestamp fields; NULL values exist in: "
            + ", ".join(null_columns)
            + ". Remediate these rows before retrying the migration."
        )

    duplicate_slug = bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM knowledge_bases
                GROUP BY workspace_id, slug
                HAVING COUNT(*) > 1
            )
            """
        )
    ).scalar()
    if duplicate_slug:
        raise RuntimeError(
            "Cannot enforce Knowledge Base slug uniqueness: duplicate "
            "(workspace_id, slug) values exist. Remediate duplicates before "
            "retrying the migration."
        )

    for table, name, _columns in DUPLICATE_UNIQUE_CONSTRAINTS:
        op.drop_constraint(name, table, type_="unique")

    for table, column in REQUIRED_TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )

    op.create_unique_constraint(
        "uq_knowledge_bases_workspace_slug",
        "knowledge_bases",
        ["workspace_id", "slug"],
    )

    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade():
    for table, name, columns in DUPLICATE_UNIQUE_CONSTRAINTS:
        op.create_unique_constraint(name, table, columns)

    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)

    op.drop_constraint(
        "uq_knowledge_bases_workspace_slug",
        "knowledge_bases",
        type_="unique",
    )

    for table, column in reversed(REQUIRED_TIMESTAMP_COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
