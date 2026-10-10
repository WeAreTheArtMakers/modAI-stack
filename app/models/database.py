from datetime import datetime
from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func
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
    assistant_preference: Mapped["AssistantPreference | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class AssistantPreference(Base):
    __tablename__ = "assistant_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_name: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="modAI",
        server_default="modAI",
    )
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="auto", server_default="auto"
    )
    tone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="professional",
        server_default="professional",
    )
    response_length: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default="balanced",
        server_default="balanced",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    user: Mapped[User] = relationship(back_populates="assistant_preference")

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_assistant_preferences_user_id"),
        CheckConstraint(
            "length(assistant_name) BETWEEN 1 AND 32",
            name="ck_assistant_preferences_name_length",
        ),
        CheckConstraint(
            "language IN ('auto', 'en', 'tr')",
            name="ck_assistant_preferences_language",
        ),
        CheckConstraint(
            "tone IN ('professional', 'friendly', 'technical', 'concise')",
            name="ck_assistant_preferences_tone",
        ),
        CheckConstraint(
            "response_length IN ('short', 'balanced', 'detailed')",
            name="ck_assistant_preferences_response_length",
        ),
    )

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="organization", cascade="all, delete-orphan")

class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
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
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_knowledge_bases_workspace_slug"),)

class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
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
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
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
    source_revision: Mapped[int] = mapped_column(
        BigInteger,
        default=1,
        server_default="1",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    # An archived (obsolete) document stays listed and indexed but is never
    # retrieved. Not a source change: no revision or source event.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship()
    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "source_revision > 0",
            name="ck_documents_source_revision",
        ),
    )

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
class IndexGeneration(Base):
    __tablename__ = "index_generations"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    generation_number: Mapped[int] = mapped_column(Integer)
    profile_id: Mapped[str] = mapped_column(String(100))
    profile_version: Mapped[int] = mapped_column(Integer)

    space_json: Mapped[dict] = mapped_column(JSON)
    space_sha256: Mapped[str] = mapped_column(String(64))

    materialization_json: Mapped[dict] = mapped_column(JSON)
    materialization_sha256: Mapped[str] = mapped_column(String(64))

    qdrant_collection: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="planned")

    baseline_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    validation_json: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
    )
    retire_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "generation_number",
            name="uq_index_generations_workspace_number",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_index_generations_workspace_id",
        ),
        CheckConstraint(
            "state IN ('planned','building','catching_up','validating',"
            "'ready','failed','superseded','retired')",
            name="ck_index_generations_state",
        ),
        CheckConstraint(
            "generation_number > 0",
            name="ck_index_generations_number_positive",
        ),
        CheckConstraint(
            "profile_version > 0",
            name="ck_index_generations_profile_version_positive",
        ),
        Index(
            "ix_index_generations_workspace_state",
            "workspace_id",
            "state",
        ),
    )


class WorkspaceRetrievalAssignment(Base):
    __tablename__ = "workspace_retrieval_assignments"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    serving_mode: Mapped[str] = mapped_column(
        String(20),
        default="legacy",
    )
    active_generation_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    assignment_epoch: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "active_generation_id"],
            ["index_generations.workspace_id", "index_generations.id"],
            name="fk_workspace_retrieval_assignment_generation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "("
            "serving_mode = 'legacy' AND active_generation_id IS NULL"
            ") OR ("
            "serving_mode = 'generation' AND active_generation_id IS NOT NULL"
            ")",
            name="ck_workspace_retrieval_assignment_mode",
        ),
        CheckConstraint(
            "assignment_epoch >= 0",
            name="ck_workspace_retrieval_assignment_epoch",
        ),
    )


class DocumentIndexEvent(Base):
    __tablename__ = "document_index_events"

    event_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )

    organization_id: Mapped[int] = mapped_column(Integer)
    workspace_id: Mapped[int] = mapped_column(Integer)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)

    # Intentionally no FK to documents: tombstones must survive source deletion.
    document_id: Mapped[int] = mapped_column(Integer)

    source_revision: Mapped[int] = mapped_column(BigInteger)
    operation: Mapped[str] = mapped_column(String(40))

    document_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "document_id",
            "source_revision",
            name="uq_document_index_events_source_revision",
        ),
        CheckConstraint(
            "source_revision > 0",
            name="ck_document_index_events_source_revision",
        ),
        Index(
            "ix_document_index_events_workspace_event",
            "workspace_id",
            "event_id",
        ),
    )


class IndexGenerationItem(Base):
    __tablename__ = "index_generation_items"

    generation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("index_generations.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Intentionally no FK to documents: migration state survives tombstones.
    document_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    source_revision: Mapped[int] = mapped_column(BigInteger)
    document_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    expected_chunk_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    indexed_chunk_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    state: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "source_revision > 0",
            name="ck_index_generation_items_source_revision",
        ),
        CheckConstraint(
            "indexed_chunk_count >= 0",
            name="ck_index_generation_items_indexed_count",
        ),
        CheckConstraint(
            "expected_chunk_count IS NULL OR expected_chunk_count >= 0",
            name="ck_index_generation_items_expected_count",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_index_generation_items_attempts",
        ),
    )


class IndexGenerationEventReceipt(Base):
    __tablename__ = "index_generation_event_receipts"

    generation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("index_generations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "document_index_events.event_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )

    applied_source_revision: Mapped[int] = mapped_column(BigInteger)
    result: Mapped[str] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_index_generation_event_receipts_event",
            "event_id",
        ),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_chat_sessions_user_workspace_updated",
            "user_id",
            "workspace_id",
            "updated_at",
        ),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_messages_session_id_id",
            "session_id",
            "id",
        ),
    )


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
