"""Add organization, workspace, knowledge-base and document-version entities."""
from alembic import op
import sqlalchemy as sa
revision = "0001_enterprise_entities"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(20), nullable=False, server_default="user"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("documents", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_table("chat_sessions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False))
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_table("messages", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text(), nullable=False))
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_table("organizations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(150), nullable=False), sa.Column("slug", sa.String(150), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("workspaces", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(150), nullable=False), sa.Column("slug", sa.String(150), nullable=False), sa.UniqueConstraint("organization_id", "slug"))
    op.create_table("knowledge_bases", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(150), nullable=False), sa.Column("slug", sa.String(150), nullable=False), sa.Column("description", sa.Text()))
    op.create_table("memberships", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE")), sa.Column("role", sa.String(20), nullable=False, server_default="user"), sa.UniqueConstraint("user_id", "organization_id", "workspace_id"))
    op.create_table("document_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("file_size", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="queued"), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("document_id", "version"))
    for name, column_type, foreign_key in [("organization_id", sa.Integer(), "organizations.id"), ("workspace_id", sa.Integer(), "workspaces.id"), ("knowledge_base_id", sa.Integer(), "knowledge_bases.id")]:
        op.add_column("documents", sa.Column(name, column_type, sa.ForeignKey(foreign_key, ondelete="SET NULL"), nullable=True))
    op.add_column("documents", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("index_status", sa.String(20), nullable=False, server_default="ready"))
    op.add_column("documents", sa.Column("index_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("documents", sa.Column("active_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("document_versions", sa.Column("stored_path", sa.String(1024), nullable=True))
    op.create_table("index_jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="queued"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_index_jobs_status", "index_jobs", ["status"])
    op.create_index("ix_index_jobs_document_id", "index_jobs", ["document_id"])
def downgrade():
    op.drop_index("ix_index_jobs_document_id", table_name="index_jobs")
    op.drop_index("ix_index_jobs_status", table_name="index_jobs")
    op.drop_table("index_jobs")
    op.drop_column("document_versions", "stored_path")
    for name in ["active_version", "updated_at", "index_error", "index_status", "file_size", "content_hash", "knowledge_base_id", "workspace_id", "organization_id"]: op.drop_column("documents", name)
    op.drop_table("document_versions")
    op.drop_table("memberships")
    op.drop_table("knowledge_bases")
    op.drop_table("workspaces")
    op.drop_table("organizations")
    op.drop_index("ix_messages_session_id", table_name="messages"); op.drop_table("messages")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions"); op.drop_table("chat_sessions")
    op.drop_index("ix_documents_user_id", table_name="documents"); op.drop_table("documents")
    op.drop_index("ix_users_email", table_name="users"); op.drop_table("users")
