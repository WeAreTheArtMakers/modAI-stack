from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Document, DocumentIndexEvent


SOURCE_STAGED = "source_staged"
ACTIVE_VERSION_PUBLISHED = "active_version_published"


def _require_event_scope(document: Document) -> tuple[int, int, int]:
    if (
        document.organization_id is None
        or document.workspace_id is None
        or document.knowledge_base_id is None
    ):
        raise ValueError(
            "document source event requires organization, workspace, "
            "and knowledge base scope"
        )

    return (
        document.organization_id,
        document.workspace_id,
        document.knowledge_base_id,
    )


async def lock_document_source(
    db: AsyncSession,
    document_id: int,
) -> Document:
    document = await db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if document is None:
        raise ValueError("document no longer exists")

    return document


def add_document_source_event(
    db: AsyncSession,
    *,
    document: Document,
    operation: str,
    document_version: int | None,
    content_hash: str | None,
    correlation_id: str | None = None,
) -> DocumentIndexEvent:
    organization_id, workspace_id, knowledge_base_id = (
        _require_event_scope(document)
    )

    event = DocumentIndexEvent(
        organization_id=organization_id,
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        document_id=document.id,
        source_revision=document.source_revision,
        operation=operation,
        document_version=document_version,
        content_hash=content_hash,
        correlation_id=correlation_id,
    )

    db.add(event)
    return event


def advance_document_source_revision(document: Document) -> int:
    if document.source_revision < 1:
        raise ValueError("document source revision must be positive")

    document.source_revision += 1
    return document.source_revision
