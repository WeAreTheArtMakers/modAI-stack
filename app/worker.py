import asyncio
import logging
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.database import Document, DocumentVersion, IndexJob
from app.services.documents.parser import extract_text
from app.services.jobs.redis_queue import RedisIndexQueue
from app.services.rag.chunker import chunk_text
from app.services.rag.embeddings import EmbeddingModelUnavailableError, embedding_model_unavailable_detail, get_embedding_service
from app.services.qdrant import qdrant_service
from app.services.storage import storage
logger = logging.getLogger(__name__)
async def process_job(job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(IndexJob, job_id)
        if not job or job.status in {"ready", "cancelled"}: return
        queue = RedisIndexQueue()
        lock = await queue.client.set(f"modai:indexing:lock:{job.document_id}:{job.version}", job_id, nx=True, ex=get_settings().indexing_job_timeout_seconds)
        if not lock: await queue.close(); return
        job.status = "processing"; job.attempts += 1; await db.commit()
        try:
            version = await db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == job.document_id, DocumentVersion.version == job.version))
            document = await db.get(Document, job.document_id)
            if not version or not document: raise ValueError("document version not found")
            def event(status: str, stage: str) -> dict:
                return {
                    "type": "index_progress",
                    "organization_id": document.organization_id,
                    "workspace_id": document.workspace_id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "document_id": document.id,
                    "job_id": job.id,
                    "status": status,
                    "stage": stage,
                }

            async def emit(status: str, stage: str) -> None:
                if document.workspace_id is not None:
                    await queue.publish_progress(event(status, stage), document.workspace_id)

            await emit("processing", "extracting")
            data = await storage.read(version.stored_path or "")
            content = extract_text(document.filename, data)
            await emit("processing", "chunking")
            chunks = chunk_text(content, get_settings().chunk_size, get_settings().chunk_overlap)
            await emit("processing", "embedding")
            vectors = await get_embedding_service().embed_texts(chunks)
            await emit("processing", "vector_indexing")
            is_replacement = version.version > document.active_version
            await qdrant_service.upsert_document(user_id=document.user_id, document_id=document.id, filename=document.filename, organization_id=document.organization_id, workspace_id=document.workspace_id, knowledge_base_id=document.knowledge_base_id, document_version=version.version, is_active=not is_replacement, chunks=chunks, vectors=vectors)
            if is_replacement:
                await qdrant_service.set_version_active(user_id=document.user_id, document_id=document.id, document_version=version.version, active=True)
                await qdrant_service.set_version_active(user_id=document.user_id, document_id=document.id, document_version=document.active_version, active=False)
                await qdrant_service.delete_document_vectors(user_id=document.user_id, document_id=document.id, document_version=document.active_version)
                document.active_version = version.version
            document.content = content; document.content_hash = version.content_hash; document.file_size = version.file_size; document.index_status = "ready"; document.index_error = None
            version.status = "ready"; job.status = "ready"; job.error = None
            await db.commit()
            await emit("ready", "ready")
        except EmbeddingModelUnavailableError:
            logger.warning("Index job blocked because the embedding model is unavailable", extra={"job_id": job_id})
            job.status = "failed" if job.attempts >= get_settings().indexing_max_retries else "queued"
            job.error = embedding_model_unavailable_detail()
            document = await db.get(Document, job.document_id)
            if document: document.index_status = job.status; document.index_error = job.error
            await db.commit()
            if document and document.workspace_id is not None:
                await queue.publish_progress(
                    {
                        "type": "index_progress",
                        "organization_id": document.organization_id,
                        "workspace_id": document.workspace_id,
                        "knowledge_base_id": document.knowledge_base_id,
                        "document_id": document.id,
                        "job_id": job.id,
                        "status": job.status,
                        "stage": "failed",
                    },
                    document.workspace_id,
                )
            if job.status == "queued": await queue.enqueue(job.id)
        except Exception:
            logger.exception("Index job failed", extra={"job_id": job_id})
            job.status = "failed" if job.attempts >= get_settings().indexing_max_retries else "queued"
            job.error = "Document indexing failed"
            document = await db.get(Document, job.document_id)
            if document: document.index_status = job.status; document.index_error = job.error
            await db.commit()
            if document and document.workspace_id is not None:
                await queue.publish_progress(
                    {
                        "type": "index_progress",
                        "organization_id": document.organization_id,
                        "workspace_id": document.workspace_id,
                        "knowledge_base_id": document.knowledge_base_id,
                        "document_id": document.id,
                        "job_id": job.id,
                        "status": job.status,
                        "stage": "failed",
                    },
                    document.workspace_id,
                )
            if job.status == "queued": await queue.enqueue(job.id)
        finally: await queue.close()
async def worker_main() -> None:
    queue = RedisIndexQueue()
    try:
        while True:
            job_id = await queue.dequeue(timeout=5)
            if job_id:
                try: await asyncio.wait_for(process_job(job_id), timeout=get_settings().indexing_job_timeout_seconds)
                except asyncio.TimeoutError: logger.error("Index job timed out", extra={"job_id": job_id})
    finally: await queue.close()
if __name__ == "__main__": asyncio.run(worker_main())
