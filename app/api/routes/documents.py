import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.database import Document
from app.models.schemas import DocumentResponse
from app.services.documents.parser import extract_text
from app.services.rag.chunker import chunk_text
from app.services.rag.embeddings import get_embedding_service
from app.services.qdrant import qdrant_service
router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)
@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload(file: UploadFile = File(...), user=Depends(current_user), db: AsyncSession = Depends(get_db)):
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes: raise HTTPException(413, "File too large")
    try: content = extract_text(file.filename or "", data)
    except (ValueError, UnicodeError) as exc: raise HTTPException(400, str(exc)) from exc
    filename = (file.filename or "document")[:255]
    doc = Document(user_id=int(user["sub"]), filename=filename, content=content)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    try:
        settings = get_settings()
        chunks = chunk_text(content, settings.chunk_size, settings.chunk_overlap)
        vectors = await get_embedding_service().embed_texts(chunks)
        await qdrant_service.upsert_document(
            user_id=doc.user_id, document_id=doc.id, filename=filename,
            chunks=chunks, vectors=vectors,
        )
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
