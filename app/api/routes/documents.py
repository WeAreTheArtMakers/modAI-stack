import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.database import Document, DocumentVersion, IndexJob, KnowledgeBase, Membership, Workspace
from app.models.schemas import DocumentResponse
from app.services.documents.parser import extract_text
from app.services.jobs.redis_queue import RedisIndexQueue
from app.services.qdrant import qdrant_service
from app.services.storage import storage
router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)
@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload(file: UploadFile = File(...), knowledge_base_id: int | None = Form(default=None), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes: raise HTTPException(413, "File too large")
    try: extract_text(file.filename or "", data)
    except Exception as exc: raise HTTPException(400, "Unsupported or invalid document") from exc
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
    stored_path = await storage.save(data, Path(filename).suffix)
    doc = Document(user_id=user_id, organization_id=workspace.organization_id, workspace_id=workspace.id, knowledge_base_id=kb.id, filename=filename, content="", content_hash=digest, file_size=len(data), index_status="queued")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    try:
        version = DocumentVersion(document_id=doc.id, version=1, content_hash=digest, file_size=len(data), status="queued", stored_path=stored_path)
        job = IndexJob(document_id=doc.id, version=1, status="queued")
        db.add_all([version, job])
        await db.commit()
        queue = RedisIndexQueue()
        try: await queue.enqueue(job.id)
        finally: await queue.close()
    except Exception as exc:
        logger.exception("Document indexing job could not be queued", extra={"document_id": doc.id})
        await storage.delete(stored_path)
        await db.delete(doc)
        await db.commit()
        raise HTTPException(503, "Document indexing job could not be queued") from exc
    return doc
@router.get("", response_model=list[DocumentResponse])
async def list_documents(user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    return list((await db.scalars(select(Document).where(Document.user_id == int(user["sub"])).order_by(Document.id.desc()))).all())
@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc = await db.scalar(select(Document).where(Document.id == document_id, Document.user_id == int(user["sub"])))
    if not doc: raise HTTPException(404, "Document not found")
    return doc
@router.get("/{document_id}/versions")
async def list_versions(document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc = await db.scalar(select(Document).where(Document.id == document_id, Document.user_id == int(user["sub"])))
    if not doc: raise HTTPException(404, "Document not found")
    return [{"version": v.version, "status": v.status, "content_hash": v.content_hash, "file_size": v.file_size, "created_at": v.created_at} for v in doc.versions]
@router.post("/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_document(document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc = await db.scalar(select(Document).where(Document.id == document_id, Document.user_id == int(user["sub"])))
    if not doc: raise HTTPException(404, "Document not found")
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.version == doc.active_version))
    if not version: raise HTTPException(409, "Document has no source version")
    job = IndexJob(document_id=doc.id, version=version.version, status="queued")
    doc.index_status = "queued"; doc.index_error = None; db.add(job); await db.commit()
    queue = RedisIndexQueue()
    try: await queue.enqueue(job.id)
    finally: await queue.close()
    return doc
@router.post("/upload-batch", response_model=list[DocumentResponse], status_code=201)
async def upload_batch(files: list[UploadFile] = File(...), knowledge_base_id: int | None = Form(default=None), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    results = []
    for file in files:
        try: results.append(await upload(file=file, knowledge_base_id=knowledge_base_id, user=user, db=db))
        except HTTPException as exc: logger.warning("Batch item rejected", extra={"filename": file.filename, "status_code": exc.status_code})
    if not results: raise HTTPException(400, "No files were accepted")
    return results
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
