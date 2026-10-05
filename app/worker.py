import asyncio
import logging
import time
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.database import Document, DocumentVersion, IndexJob
from app.services.documents.parser import extract_text
from app.services.document_source_events import (
    ACTIVE_VERSION_PUBLISHED,
    add_document_source_event,
    advance_document_source_revision,
    lock_document_source,
)
from app.services.jobs.redis_queue import RedisIndexQueue
from app.services.rag.chunker import chunk_text
from app.services.rag.embeddings import EmbeddingModelUnavailableError, embedding_model_unavailable_detail, get_embedding_service
from app.services.qdrant import qdrant_service
from app.services.storage import storage
from app.services.observability import metrics
logger = logging.getLogger(__name__)
async def process_job(job_id: str) -> None:
    started = time.perf_counter()
    async with SessionLocal() as db:
        job = await db.get(IndexJob, job_id)
        if not job or job.status in {"ready", "cancelled"}: return
        queue = RedisIndexQueue()
        lock_key = f"modai:indexing:lock:{job.document_id}:{job.version}"
        lock = await queue.client.set(lock_key, job_id, nx=True, ex=get_settings().indexing_job_timeout_seconds)
        if not lock: await queue.close(); return
        job.status = "processing"; job.attempts += 1; await db.commit()
        logger.info("Index job started", extra={"component": "worker", "job_id": job.id, "document_id": job.document_id, "attempt": job.attempts})
        try:
            version = await db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == job.document_id,
                    DocumentVersion.version == job.version,
                )
            )
            document = await db.get(
                Document,
                job.document_id,
            )

            if not version or not document:
                raise ValueError(
                    "document version not found"
                )

            # A ready version means this job is a reindex/repair of an
            # already-published source. It must not create a new source
            # revision or publication event.
            version_was_ready = version.status == "ready"

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

            async def emit(
                status: str,
                stage: str,
            ) -> None:
                if document.workspace_id is not None:
                    await queue.publish_progress(
                        event(status, stage),
                        document.workspace_id,
                    )

            await emit(
                "processing",
                "extracting",
            )

            data = await storage.read(
                version.stored_path or ""
            )
            content = extract_text(
                document.filename,
                data,
            )

            await emit(
                "processing",
                "chunking",
            )

            chunks = chunk_text(
                content,
                get_settings().chunk_size,
                get_settings().chunk_overlap,
            )

            await emit(
                "processing",
                "embedding",
            )

            vectors = await get_embedding_service().embed_texts(
                chunks
            )

            await emit(
                "processing",
                "vector_indexing",
            )

            # Heavy extraction/embedding happens before the PostgreSQL
            # lock. Publication itself is serialized per document.
            locked_document = await lock_document_source(
                db,
                job.document_id,
            )
            document = locked_document

            active_version_before = (
                locked_document.active_version
            )

            stale = (
                version.version
                < active_version_before
            )

            active_reindex = (
                version.version == active_version_before
                and version_was_ready
            )

            publishes_source = (
                not stale
                and not active_reindex
            )

            replacement_publication = (
                publishes_source
                and version.version
                > active_version_before
            )

            qdrant_args = {
                "user_id": locked_document.user_id,
                "document_id": locked_document.id,
                "filename": locked_document.filename,
                "organization_id": locked_document.organization_id,
                "workspace_id": locked_document.workspace_id,
                "knowledge_base_id": locked_document.knowledge_base_id,
                "document_version": version.version,
                "chunks": chunks,
                "vectors": vectors,
            }

            if stale:
                # An older staged version finished after a newer source
                # became active. Keep it non-active and never move the
                # SQL source pointer backwards.
                await qdrant_service.upsert_document(
                    **qdrant_args,
                    is_active=False,
                )

            elif replacement_publication:
                # Materialize the candidate version first. The active
                # swap remains serialized by the PostgreSQL row lock.
                await qdrant_service.upsert_document(
                    **qdrant_args,
                    is_active=False,
                )

                await qdrant_service.set_version_active(
                    user_id=locked_document.user_id,
                    document_id=locked_document.id,
                    document_version=version.version,
                    active=True,
                )

                await qdrant_service.set_version_active(
                    user_id=locked_document.user_id,
                    document_id=locked_document.id,
                    document_version=active_version_before,
                    active=False,
                )

                await qdrant_service.delete_document_vectors(
                    user_id=locked_document.user_id,
                    document_id=locked_document.id,
                    document_version=active_version_before,
                )

            else:
                # Initial publication and active-version reindex both
                # materialize the current SQL version as active.
                await qdrant_service.upsert_document(
                    **qdrant_args,
                    is_active=True,
                )

            if stale:
                # Indexing completed, but this source lost the race to a
                # newer publication. Do not touch Document source state.
                version.status = "ready"
                job.status = "ready"
                job.error = None

            else:
                if replacement_publication:
                    locked_document.active_version = (
                        version.version
                    )

                locked_document.content = content
                locked_document.content_hash = (
                    version.content_hash
                )
                locked_document.file_size = (
                    version.file_size
                )
                locked_document.index_status = "ready"
                locked_document.index_error = None

                if publishes_source:
                    advance_document_source_revision(
                        locked_document
                    )

                    add_document_source_event(
                        db,
                        document=locked_document,
                        operation=ACTIVE_VERSION_PUBLISHED,
                        document_version=version.version,
                        content_hash=version.content_hash,
                        correlation_id=job.id,
                    )

                version.status = "ready"
                job.status = "ready"
                job.error = None

            await db.commit()

            metrics.event(
                "indexing_jobs",
                "ready",
            )

            logger.info(
                "Index job completed",
                extra={
                    "component": "worker",
                    "job_id": job.id,
                    "document_id": job.document_id,
                    "attempt": job.attempts,
                    "duration_ms": round(
                        (
                            time.perf_counter()
                            - started
                        )
                        * 1000,
                        1,
                    ),
                },
            )

            await emit(
                "ready",
                "ready",
            )

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
            metrics.event("indexing_jobs", job.status)
            logger.warning("Index job retry or failure", extra={"component": "worker", "job_id": job.id, "document_id": job.document_id, "attempt": job.attempts, "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
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
            metrics.event("indexing_jobs", job.status)
            logger.error("Index job failed", extra={"component": "worker", "job_id": job.id, "document_id": job.document_id, "attempt": job.attempts, "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
        finally:
            try:
                await queue.client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0",
                    1,
                    lock_key,
                    job_id,
                )
            except Exception:
                logger.warning("Index job lock could not be released", extra={"job_id": job_id})
            await queue.close()
async def worker_main() -> None:
    queue = RedisIndexQueue()
    try:
        while True:
            job_id = await queue.dequeue(timeout=5)
            if job_id:
                try: await asyncio.wait_for(process_job(job_id), timeout=get_settings().indexing_job_timeout_seconds)
                except asyncio.TimeoutError:
                    metrics.event("indexing_jobs", "timeout")
                    logger.error("Index job timed out", extra={"component": "worker", "job_id": job_id})
    finally: await queue.close()
if __name__ == "__main__": asyncio.run(worker_main())
