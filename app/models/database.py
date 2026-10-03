from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from uuid import uuid4
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="organization", cascade="all, delete-orphan")

class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(150))
    organization: Mapped[Organization] = relationship(back_populates="workspaces")
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace: Mapped[Workspace] = relationship(back_populates="knowledge_bases")
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)

class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="user")
    user: Mapped[User] = relationship(back_populates="memberships")
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", "workspace_id"),
        # PostgreSQL needs a partial index because NULL values in a normal
        # unique constraint are distinct. The migration owns deployment;
        # metadata mirrors it for development/test create_all environments.
        Index(
            "uq_memberships_user_org_orglevel",
            "user_id",
            "organization_id",
            unique=True,
            postgresql_where=workspace_id.is_(None),
            sqlite_where=workspace_id.is_(None),
        ),
    )


class Invitation(Base):
    """A one-time tenant invitation with no stored raw credential."""
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="user")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stored_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped["Document"] = relationship(back_populates="versions")
    __table_args__ = (UniqueConstraint("document_id", "version"),)
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    knowledge_base_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    index_status: Mapped[str] = mapped_column(String(20), default="ready")
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship()
    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="document", cascade="all, delete-orphan")

class IndexJob(Base):
    __tablename__ = "index_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
