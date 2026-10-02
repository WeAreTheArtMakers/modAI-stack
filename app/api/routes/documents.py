import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.authorization import authorized_workspaces, require_document_access, require_knowledge_base_access
from app.api.deps import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.database import Document, DocumentVersion, IndexJob
from app.models.schemas import DocumentListResponse, DocumentResponse
from app.services.documents.parser import extract_text
from app.services.jobs.redis_queue import RedisIndexQueue
from app.services.qdrant import qdrant_service
from app.services.storage import storage
from app.services.audit import record_audit_event
router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)
@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload(request: Request, file: UploadFile = File(...), knowledge_base_id: int | None = Form(default=None), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes: raise HTTPException(413, "File too large")
    try: extract_text(file.filename or "", data)
    except Exception as exc: raise HTTPException(400, "Unsupported or invalid document") from exc
    filename = (file.filename or "document")[:255]
    user_id = int(user["sub"])
    if knowledge_base_id is None: raise HTTPException(400, "knowledge_base_id is required")
    kb, workspace, membership = await require_knowledge_base_access(db, user, knowledge_base_id, "manager")
    digest = hashlib.sha256(data).hexdigest()
    duplicate = await db.scalar(select(Document).where(Document.knowledge_base_id == kb.id, Document.content_hash == digest))
    if duplicate: raise HTTPException(409, "This document already exists in the knowledge base")
    stored_path = await storage.save(data, Path(filename).suffix)
    doc = Document(user_id=user_id, organization_id=workspace.organization_id, workspace_id=workspace.id, knowledge_base_id=kb.id, filename=filename, content="", content_hash=digest, file_size=len(data), index_status="queued")
    db.add(doc)
    await db.flush()
    record_audit_event(db, action="document_upload", resource_type="document", actor_user_id=user_id, organization_id=workspace.organization_id, workspace_id=workspace.id, resource_id=doc.id, metadata={"file_size": len(data)}, request=request)
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
@router.get("", response_model=DocumentListResponse)
async def list_documents(
    knowledge_base_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if knowledge_base_id is not None:
        knowledge_base, workspace, _ = await require_knowledge_base_access(db, user, knowledge_base_id)
        filters = [
            Document.knowledge_base_id == knowledge_base.id,
            Document.workspace_id == workspace.id,
            Document.organization_id == workspace.organization_id,
        ]
    else:
        workspace_ids = [workspace.id for workspace, _, _ in await authorized_workspaces(db, user)]
        if not workspace_ids:
            return DocumentListResponse(items=[], total=0, limit=limit, offset=offset)
        filters = [Document.workspace_id.in_(workspace_ids)]

    base_query = select(Document).where(*filters)
    total = await db.scalar(select(func.count()).select_from(base_query.subquery()))
    documents = list((await db.scalars(
        base_query.order_by(Document.id.desc()).offset(offset).limit(limit)
    )).all())
    return DocumentListResponse(items=documents, total=total or 0, limit=limit, offset=offset)
@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc, _ = await require_document_access(db, user, document_id)
    return doc
@router.get("/{document_id}/versions")
async def list_versions(document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc, _ = await require_document_access(db, user, document_id)
    versions = list((await db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version)
    )).all())
    return [{"version": v.version, "status": v.status, "content_hash": v.content_hash, "file_size": v.file_size, "created_at": v.created_at} for v in versions]
@router.post("/{document_id}/reindex", response_model=DocumentResponse)
async def reindex_document(request: Request, document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc, _ = await require_document_access(db, user, document_id, "manager")
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id, DocumentVersion.version == doc.active_version))
    if not version: raise HTTPException(409, "Document has no source version")
    job = IndexJob(document_id=doc.id, version=version.version, status="queued")
    doc.index_status = "queued"; doc.index_error = None; db.add(job); record_audit_event(db, action="document_reindex", resource_type="document", actor_user_id=int(user["sub"]), organization_id=doc.organization_id, workspace_id=doc.workspace_id, resource_id=doc.id, request=request); await db.commit(); await db.refresh(doc)
    queue = RedisIndexQueue()
    try: await queue.enqueue(job.id)
    finally: await queue.close()
    return doc
@router.post("/{document_id}/replace", response_model=DocumentResponse)
async def replace_document(request: Request, document_id: int, file: UploadFile = File(...), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc, _ = await require_document_access(db, user, document_id, "manager")
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes: raise HTTPException(413, "File too large")
    try: extract_text(file.filename or doc.filename, data)
    except Exception as exc: raise HTTPException(400, "Unsupported or invalid document") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest == doc.content_hash: raise HTTPException(409, "Replacement has identical content")
    versions = await db.scalars(select(DocumentVersion.version).where(DocumentVersion.document_id == doc.id))
    next_version = max(list(versions), default=doc.active_version) + 1
    path = await storage.save(data, Path(file.filename or doc.filename).suffix)
    version = DocumentVersion(document_id=doc.id, version=next_version, content_hash=digest, file_size=len(data), status="queued", stored_path=path)
    job = IndexJob(document_id=doc.id, version=next_version, status="queued")
    doc.filename = (file.filename or doc.filename)[:255]; doc.index_status = "queued"; doc.index_error = None
    db.add_all([version, job]); record_audit_event(db, action="document_replace", resource_type="document", actor_user_id=int(user["sub"]), organization_id=doc.organization_id, workspace_id=doc.workspace_id, resource_id=doc.id, metadata={"version": next_version}, request=request); await db.commit(); await db.refresh(doc)
    queue = RedisIndexQueue()
    try: await queue.enqueue(job.id)
    finally: await queue.close()
    return doc
@router.post("/upload-batch", response_model=list[DocumentResponse], status_code=201)
async def upload_batch(request: Request, files: list[UploadFile] = File(...), knowledge_base_id: int | None = Form(default=None), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    results = []
    for file in files:
        try: results.append(await upload(file=file, knowledge_base_id=knowledge_base_id, request=request, user=user, db=db))
        except HTTPException as exc: logger.warning("Batch item rejected", extra={"filename": file.filename, "status_code": exc.status_code})
    if not results: raise HTTPException(400, "No files were accepted")
    return results
@router.delete("/{document_id}", status_code=204)
async def delete_document(request: Request, document_id: int, user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    doc, _ = await require_document_access(db, user, document_id, "manager")
    try:
        await qdrant_service.delete_document_vectors(user_id=doc.user_id, document_id=doc.id)
    except Exception as exc:
        logger.exception("Document vector deletion failed", extra={"document_id": doc.id})
        raise HTTPException(503, "Document vector deletion failed") from exc
    versions = list((await db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))).all())
    jobs = list((await db.scalars(select(IndexJob).where(IndexJob.document_id == doc.id, IndexJob.status.in_(["queued", "processing"])))).all())
    for job in jobs: job.status = "cancelled"
    for version in versions: await storage.delete(version.stored_path)
    record_audit_event(db, action="document_delete", resource_type="document", actor_user_id=int(user["sub"]), organization_id=doc.organization_id, workspace_id=doc.workspace_id, resource_id=doc.id, request=request)
    await db.delete(doc); await db.commit()
