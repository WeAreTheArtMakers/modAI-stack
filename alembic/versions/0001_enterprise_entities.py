"""Add organization, workspace, knowledge-base and document-version entities."""
from alembic import op
import sqlalchemy as sa
revision = "0001_enterprise_entities"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("organizations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(150), nullable=False), sa.Column("slug", sa.String(150), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("workspaces", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(150), nullable=False), sa.Column("slug", sa.String(150), nullable=False), sa.UniqueConstraint("organization_id", "slug"))
    op.create_table("knowledge_bases", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(150), nullable=False), sa.Column("slug", sa.String(150), nullable=False), sa.Column("description", sa.Text()))
    op.create_table("memberships", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE")), sa.Column("role", sa.String(20), nullable=False, server_default="user"), sa.UniqueConstraint("user_id", "organization_id", "workspace_id"))
    op.create_table("document_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("file_size", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="queued"), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("document_id", "version"))
    for name, column in [("organization_id", sa.Integer()), ("workspace_id", sa.Integer()), ("knowledge_base_id", sa.Integer()), ("content_hash", sa.String(64)), ("file_size", sa.Integer()), ("index_status", sa.String(20)), ("index_error", sa.Text()), ("updated_at", sa.DateTime(timezone=True))]: op.add_column("documents", sa.Column(name, column, nullable=True))
def downgrade():
    for name in ["updated_at", "index_error", "index_status", "file_size", "content_hash", "knowledge_base_id", "workspace_id", "organization_id"]: op.drop_column("documents", name)
    op.drop_table("document_versions")
    op.drop_table("memberships")
    op.drop_table("knowledge_bases")
    op.drop_table("workspaces")
    op.drop_table("organizations")
