import hashlib
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.database import Document, DocumentVersion, KnowledgeBase, Membership, Workspace
from app.models.schemas import DocumentResponse
from app.services.documents.parser import extract_text
from app.services.rag.chunker import chunk_text
from app.services.rag.embeddings import get_embedding_service
from app.services.qdrant import qdrant_service
router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)
@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload(file: UploadFile = File(...), knowledge_base_id: int | None = Form(default=None), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes: raise HTTPException(413, "File too large")
    try: content = extract_text(file.filename or "", data)
    except (ValueError, UnicodeError) as exc: raise HTTPException(400, str(exc)) from exc
    filename = (file.filename or "document")[:255]
    user_id = int(user["sub"])
    kb_query = select(KnowledgeBase, Workspace, Membership).join(Workspace, KnowledgeBase.workspace_id == Workspace.id).join(Membership, Membership.workspace_id == Workspace.id).where(Membership.user_id == user_id)
    if knowledge_base_id is not None: kb_query = kb_query.where(KnowledgeBase.id == knowledge_base_id)
    kb_row = (await db.execute(kb_query)).first()
    if not kb_row: raise HTTPException(403, "Knowledge base access required")
    kb, workspace, membership = kb_row
    digest = hashlib.sha256(data).hexdigest()
    duplicate = await db.scalar(select(Document).where(Document.knowledge_base_id == kb.id, Document.content_hash == digest))
    if duplicate: raise HTTPException(409, "This document already exists in the knowledge base")
    doc = Document(user_id=user_id, organization_id=workspace.organization_id, workspace_id=workspace.id, knowledge_base_id=kb.id, filename=filename, content=content, content_hash=digest, file_size=len(data), index_status="processing")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    try:
        settings = get_settings()
        chunks = chunk_text(content, settings.chunk_size, settings.chunk_overlap)
        vectors = await get_embedding_service().embed_texts(chunks)
        await qdrant_service.upsert_document(
            user_id=doc.user_id, document_id=doc.id, filename=filename,
            organization_id=doc.organization_id, workspace_id=doc.workspace_id,
            knowledge_base_id=doc.knowledge_base_id, chunks=chunks, vectors=vectors,
        )
        doc.index_status = "ready"
        doc.versions.append(DocumentVersion(document_id=doc.id, version=1, content_hash=digest, file_size=len(data), status="ready"))
        await db.commit()
    except Exception as exc:
        logger.exception("Document vector ingestion failed", extra={"document_id": doc.id})
        try:
            await qdrant_service.delete_document_vectors(user_id=doc.user_id, document_id=doc.id)
        except Exception:
            logger.exception("Failed to clean up partial document vectors", extra={"document_id": doc.id})
        await db.delete(doc)
        await db.commit()
        raise HTTPException(503, "Document indexing failed") from exc
    return doc
@router.get("", response_model=list[DocumentResponse])
async def list_documents(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    return list((await db.scalars(select(Document).where(Document.user_id == int(user["sub"])).order_by(Document.id.desc()))).all())
@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc = await db.scalar(select(Document).where(Document.id == document_id, Document.user_id == int(user["sub"])))
    if not doc: raise HTTPException(404, "Document not found")
    try:
        await qdrant_service.delete_document_vectors(user_id=doc.user_id, document_id=doc.id)
    except Exception as exc:
        logger.exception("Document vector deletion failed", extra={"document_id": doc.id})
        raise HTTPException(503, "Document vector deletion failed") from exc
    await db.delete(doc); await db.commit()
