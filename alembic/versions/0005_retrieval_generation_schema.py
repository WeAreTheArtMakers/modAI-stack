"""Add retrieval generation and durable source-event schema groundwork."""

from alembic import op
import sqlalchemy as sa


revision = "0005_retrieval_generation_schema"
down_revision = "0004_membership_invariants"
branch_labels = None
depends_on = None


EVENT_ID_TYPE = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade():
    # Existing source rows start at revision 1. This does not create events,
    # change serving behavior, or reinterpret legacy Qdrant provenance.
    op.add_column(
        "documents",
        sa.Column(
            "source_revision",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_documents_deleted_at",
        "documents",
        ["deleted_at"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_documents_source_revision",
        "documents",
        "source_revision > 0",
    )

    op.create_table(
        "index_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.String(100), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("space_json", sa.JSON(), nullable=False),
        sa.Column("space_sha256", sa.String(64), nullable=False),
        sa.Column("materialization_json", sa.JSON(), nullable=False),
        sa.Column("materialization_sha256", sa.String(64), nullable=False),
        sa.Column("qdrant_collection", sa.String(64), nullable=False),
        sa.Column(
            "state",
            sa.String(30),
            nullable=False,
            server_default="planned",
        ),
        sa.Column("baseline_event_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "validation_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "retire_after",
            sa.DateTime(timezone=True),
            nullable=True,
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
            "workspace_id",
            "generation_number",
            name="uq_index_generations_workspace_number",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_index_generations_workspace_id",
        ),
        sa.CheckConstraint(
            "state IN ('planned','building','catching_up','validating',"
            "'ready','failed','superseded','retired')",
            name="ck_index_generations_state",
        ),
        sa.CheckConstraint(
            "generation_number > 0",
            name="ck_index_generations_number_positive",
        ),
        sa.CheckConstraint(
            "profile_version > 0",
            name="ck_index_generations_profile_version_positive",
        ),
    )
    op.create_index(
        "ix_index_generations_workspace_id",
        "index_generations",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_index_generations_workspace_state",
        "index_generations",
        ["workspace_id", "state"],
        unique=False,
    )

    op.create_table(
        "workspace_retrieval_assignments",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "serving_mode",
            sa.String(20),
            nullable=False,
            server_default="legacy",
        ),
        sa.Column(
            "active_generation_id",
            sa.String(36),
            nullable=True,
        ),
        sa.Column(
            "assignment_epoch",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "active_generation_id"],
            ["index_generations.workspace_id", "index_generations.id"],
            name="fk_workspace_retrieval_assignment_generation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "("
            "serving_mode = 'legacy' AND active_generation_id IS NULL"
            ") OR ("
            "serving_mode = 'generation' AND active_generation_id IS NOT NULL"
            ")",
            name="ck_workspace_retrieval_assignment_mode",
        ),
        sa.CheckConstraint(
            "assignment_epoch >= 0",
            name="ck_workspace_retrieval_assignment_epoch",
        ),
    )

    op.create_table(
        "document_index_events",
        sa.Column(
            "event_id",
            EVENT_ID_TYPE,
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        # No documents FK: delete tombstones must outlive the source row.
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "document_id",
            "source_revision",
            name="uq_document_index_events_source_revision",
        ),
        sa.CheckConstraint(
            "source_revision > 0",
            name="ck_document_index_events_source_revision",
        ),
    )
    op.create_index(
        "ix_document_index_events_workspace_event",
        "document_index_events",
        ["workspace_id", "event_id"],
        unique=False,
    )

    op.create_table(
        "index_generation_items",
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey(
                "index_generations.id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        # No documents FK: state survives logical/hard source deletion.
        sa.Column(
            "document_id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column("source_revision", sa.BigInteger(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("expected_chunk_count", sa.Integer(), nullable=True),
        sa.Column(
            "indexed_chunk_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "state",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(100), nullable=True),
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
        sa.CheckConstraint(
            "source_revision > 0",
            name="ck_index_generation_items_source_revision",
        ),
        sa.CheckConstraint(
            "indexed_chunk_count >= 0",
            name="ck_index_generation_items_indexed_count",
        ),
        sa.CheckConstraint(
            "expected_chunk_count IS NULL OR expected_chunk_count >= 0",
            name="ck_index_generation_items_expected_count",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_index_generation_items_attempts",
        ),
    )
    op.create_index(
        "ix_index_generation_items_state",
        "index_generation_items",
        ["state"],
        unique=False,
    )

    op.create_table(
        "index_generation_event_receipts",
        sa.Column(
            "generation_id",
            sa.String(36),
            sa.ForeignKey(
                "index_generations.id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column(
            "event_id",
            EVENT_ID_TYPE,
            sa.ForeignKey(
                "document_index_events.event_id",
                ondelete="RESTRICT",
            ),
            primary_key=True,
        ),
        sa.Column(
            "applied_source_revision",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_index_generation_event_receipts_event",
        "index_generation_event_receipts",
        ["event_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_index_generation_event_receipts_event",
        table_name="index_generation_event_receipts",
    )
    op.drop_table("index_generation_event_receipts")

    op.drop_index(
        "ix_index_generation_items_state",
        table_name="index_generation_items",
    )
    op.drop_table("index_generation_items")

    op.drop_index(
        "ix_document_index_events_workspace_event",
        table_name="document_index_events",
    )
    op.drop_table("document_index_events")

    op.drop_table("workspace_retrieval_assignments")

    op.drop_index(
        "ix_index_generations_workspace_state",
        table_name="index_generations",
    )
    op.drop_index(
        "ix_index_generations_workspace_id",
        table_name="index_generations",
    )
    op.drop_table("index_generations")

    op.drop_constraint(
        "ck_documents_source_revision",
        "documents",
        type_="check",
    )
    op.drop_index(
        "ix_documents_deleted_at",
        table_name="documents",
    )
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "source_revision")
