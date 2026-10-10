"""Retrieval from a validated index generation (design #27, reduced).

A workspace serves RAG from an index generation only when all of these hold:
- the deployment sets RETRIEVAL_GENERATIONS_ENABLED=true;
- its ``workspace_retrieval_assignments`` row says ``serving_mode='generation'``;
- the referenced generation belongs to that workspace, is ``ready`` (it passed
  ``app.tools.retrieval_generation validate``), and its stored contracts hash to their recorded
  SHA-256 values and match a reviewed registry candidate.

Workspaces without a row, or in ``legacy`` mode, keep the existing MiniLM ``rag_documents`` path
unchanged. A generation-mode workspace never falls back to the legacy collection: if anything above
fails, retrieval raises ``RetrievalIndexUnavailableError`` (HTTP 503 / WebSocket error).

The worker keeps an active generation current: every source it publishes in a generation-mode
workspace is written to the legacy collection (the rollback copy) and to the active generation
(``mirror_to_active_generation``). Deleted documents are tombstoned in PostgreSQL and their points
are dropped at query time by ``live_generation_hits``, as are the points of archived documents. Not
implemented (design prerequisites for a multi-workspace rollout): outbox replay, the activation
write gate, and admin APIs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.database import (
    Document,
    DocumentIndexEvent,
    DocumentVersion,
    IndexGeneration,
    IndexGenerationItem,
    WorkspaceRetrievalAssignment,
)
from app.services.rag.chunker import chunk_text
from app.services.rag.generation_qdrant import GenerationQdrantAdapter
from app.services.rag.retrieval_contract_registry import (
    ReviewedEmbeddingCandidate,
    get_reviewed_candidate,
)
from app.services.rag.retrieval_contracts import (
    AuthorizedTenantGeneration,
    EmbeddingSpaceContract,
    GenerationWriteScope,
    LegacyUnverifiedRetrieval,
    MaterializationContract,
    ResolvedGenerationWriteIndex,
    ResolvedRetrievalIndex,
    RetrievalCompatibilityError,
    collection_name_for_space,
    validate_vector,
)

logger = logging.getLogger(__name__)

# How generations turn a source into chunks: the same word chunker and sizes as the legacy path
# (app.services.rag.chunker, CHUNK_SIZE=700 / CHUNK_OVERLAP=100), so MiniLM and BGE-M3 compare on
# identical chunks.
WORD_CHUNKS_V1 = MaterializationContract(
    schema_version=1,
    chunker_id="modai-word-split-v1",
    chunk_size=700,
    chunk_overlap=100,
    payload_schema_version="generation-payload-v1",
)
_MATERIALIZATIONS = {WORD_CHUNKS_V1.materialization_sha256: WORD_CHUNKS_V1}


class RetrievalIndexUnavailableError(RuntimeError):
    """The workspace's retrieval index cannot be used safely; never fall back to another index."""


def retrieval_index_unavailable_detail() -> str:
    return "Retrieval index unavailable for this workspace. An administrator must check its index generation."


def generations_enabled() -> bool:
    return get_settings().retrieval_generations_enabled


@dataclass(frozen=True, slots=True)
class GenerationContracts:
    candidate: ReviewedEmbeddingCandidate
    space: EmbeddingSpaceContract
    materialization: MaterializationContract
    collection_name: str


def generation_contracts(generation: IndexGeneration) -> GenerationContracts:
    """The generation's stored contracts, verified against their hashes and the reviewed registry."""
    candidate = get_reviewed_candidate(generation.profile_id, generation.profile_version)
    if candidate is None:
        raise RetrievalCompatibilityError("generation profile is not a reviewed candidate")
    try:
        space = EmbeddingSpaceContract(**generation.space_json)
        materialization = MaterializationContract(**generation.materialization_json)
    except (TypeError, ValueError) as exc:
        raise RetrievalCompatibilityError("generation contract document is invalid") from exc
    if space.space_sha256 != generation.space_sha256 or space.space_sha256 != candidate.space.space_sha256:
        raise RetrievalCompatibilityError("generation embedding-space hash mismatch")
    if materialization.materialization_sha256 != generation.materialization_sha256:
        raise RetrievalCompatibilityError("generation materialization hash mismatch")
    if materialization.materialization_sha256 not in _MATERIALIZATIONS:
        raise RetrievalCompatibilityError("generation materialization is not supported")
    collection_name = collection_name_for_space(space.space_sha256)
    if generation.qdrant_collection != collection_name:
        raise RetrievalCompatibilityError("generation collection does not match its embedding space")
    return GenerationContracts(candidate, space, materialization, collection_name)


class ContractEmbedder:
    """One reviewed embedding model, loaded offline from its pinned local artifact."""

    def __init__(self, candidate: ReviewedEmbeddingCandidate, model=None):
        self.candidate = candidate
        self.space = candidate.space
        self._model = model
        self._lock = threading.Lock()

    def artifact_path(self) -> Path:
        if not self.candidate.artifact_dir:
            raise RetrievalIndexUnavailableError("embedding candidate has no provisioned artifact")
        return Path(get_settings().retrieval_model_root) / self.candidate.artifact_dir

    def _load(self):
        path = self.artifact_path()
        if self.space.model_revision not in path.name or not (path / "config.json").is_file():
            raise RetrievalIndexUnavailableError("pinned embedding artifact is not provisioned")
        weights = path / "model.safetensors"
        if self.candidate.weights_bytes is not None and (
            not weights.is_file() or weights.stat().st_size != self.candidate.weights_bytes
        ):
            raise RetrievalIndexUnavailableError("embedding weights do not match the pinned artifact")
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(str(path), device="cpu", local_files_only=True, trust_remote_code=False)
        if model.get_sentence_embedding_dimension() != self.space.dimensions:
            raise RetrievalCompatibilityError("loaded embedding model dimension mismatch")
        smoke = model.encode(["modAI"], normalize_embeddings=self.space.normalize_embeddings, convert_to_numpy=True)
        validate_vector(smoke[0].tolist(), self.space)
        return model

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load()
        return self._model

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._get_model().encode(
            list(texts),
            batch_size=4,
            normalize_embeddings=self.space.normalize_embeddings,
            convert_to_numpy=True,
        ).tolist()
        for vector in vectors:
            validate_vector(vector, self.space)
        return vectors

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, texts)

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]


_embedders: dict[str, ContractEmbedder] = {}
_embedders_lock = threading.Lock()


def get_contract_embedder(candidate: ReviewedEmbeddingCandidate) -> ContractEmbedder:
    """Process-wide model instance per immutable embedding space (never per display name)."""
    key = candidate.space.space_sha256
    with _embedders_lock:
        if key not in _embedders:
            _embedders[key] = ContractEmbedder(candidate)
        return _embedders[key]


@lru_cache
def get_generation_adapter() -> GenerationQdrantAdapter:
    return GenerationQdrantAdapter()


@dataclass(frozen=True, slots=True)
class GenerationServing:
    """The request's resolved generation: index identity plus the model of its embedding space."""

    index: ResolvedRetrievalIndex
    embedder: ContractEmbedder


async def resolve_retrieval_index(
    db: AsyncSession,
    *,
    workspace_id: int,
    organization_id: int,
    knowledge_base_ids: Sequence[int],
) -> GenerationServing | LegacyUnverifiedRetrieval:
    """Resolve once per request, after Knowledge Base authorization."""
    assignment = await db.get(WorkspaceRetrievalAssignment, workspace_id)
    if assignment is None or assignment.serving_mode == "legacy":
        return LegacyUnverifiedRetrieval()
    if not generations_enabled():
        raise RetrievalIndexUnavailableError("generation serving is not enabled in this deployment")
    generation = await db.get(IndexGeneration, assignment.active_generation_id)
    if generation is None or generation.workspace_id != workspace_id or generation.state != "ready":
        raise RetrievalIndexUnavailableError("active index generation is missing or not ready")
    contracts = generation_contracts(generation)
    index = ResolvedRetrievalIndex(
        scope=AuthorizedTenantGeneration(
            organization_id=organization_id,
            workspace_id=workspace_id,
            knowledge_base_ids=tuple(knowledge_base_ids),
            generation_id=UUID(generation.id),
        ),
        space=contracts.space,
        materialization=contracts.materialization,
        collection_name=contracts.collection_name,
        assignment_epoch=assignment.assignment_epoch,
    )
    return GenerationServing(index, get_contract_embedder(contracts.candidate))


async def live_generation_hits(db: AsyncSession, index: ResolvedRetrievalIndex, hits: list) -> list:
    """Keep hits whose document is still current in PostgreSQL: not deleted, not archived, in an
    authorized Knowledge Base, and at the same active version and source revision that was indexed.

    Archiving changes no revision, so an archived document's points stay current in the generation
    and serve again as soon as it is un-archived."""
    ids = {hit.payload["document_id"] for hit in hits}
    if not ids:
        return []
    rows = await db.execute(
        select(Document.id, Document.active_version, Document.source_revision, Document.knowledge_base_id).where(
            Document.id.in_(ids),
            Document.organization_id == index.scope.organization_id,
            Document.workspace_id == index.scope.workspace_id,
            Document.knowledge_base_id.in_(index.scope.knowledge_base_ids),
            Document.deleted_at.is_(None),
            Document.archived_at.is_(None),
        )
    )
    current = {row.id: row for row in rows}
    return [
        hit
        for hit in hits
        if (row := current.get(hit.payload["document_id"])) is not None
        and hit.payload["document_version"] == row.active_version
        and hit.payload["source_revision"] == row.source_revision
        and hit.payload["knowledge_base_id"] == row.knowledge_base_id
    ]


async def eligible_sources(db: AsyncSession, workspace_id: int, organization_id: int) -> list[tuple[Document, DocumentVersion]]:
    """Documents a generation must contain: live, scoped, with a ready active version. Archived
    documents stay included (they are filtered at query time), so un-archiving needs no reindex."""
    rows = await db.execute(
        select(Document, DocumentVersion)
        .join(
            DocumentVersion,
            (DocumentVersion.document_id == Document.id) & (DocumentVersion.version == Document.active_version),
        )
        .where(
            Document.workspace_id == workspace_id,
            Document.organization_id == organization_id,
            Document.knowledge_base_id.is_not(None),
            Document.deleted_at.is_(None),
            DocumentVersion.status == "ready",
        )
        .order_by(Document.id)
    )
    return [(document, version) for document, version in rows.all()]


def source_snapshot_sha256(sources: Sequence[tuple[Document, DocumentVersion]]) -> str:
    """Identity of the exact source state a validation covered (no content, only ids and hashes)."""
    snapshot = sorted(
        (document.id, document.knowledge_base_id, document.source_revision, version.version, version.content_hash)
        for document, version in sources
    )
    return hashlib.sha256(json.dumps(snapshot, separators=(",", ":")).encode()).hexdigest()


async def latest_source_event_id(db: AsyncSession, workspace_id: int) -> int:
    value = await db.scalar(
        select(func.max(DocumentIndexEvent.event_id)).where(DocumentIndexEvent.workspace_id == workspace_id)
    )
    return int(value or 0)


async def warm_active_generation_models(db: AsyncSession) -> None:
    """Load the models of active generations so a first question does not pay the load."""
    if not generations_enabled():
        return
    generations = await db.scalars(
        select(IndexGeneration).join(
            WorkspaceRetrievalAssignment,
            WorkspaceRetrievalAssignment.active_generation_id == IndexGeneration.id,
        ).where(WorkspaceRetrievalAssignment.serving_mode == "generation")
    )
    for generation in generations.all():
        try:
            embedder = get_contract_embedder(generation_contracts(generation).candidate)
            await embedder.embed_text("ısınma")
        except Exception:
            logger.warning("Generation embedding warm-up failed", extra={"component": "rag"})


async def mirror_to_active_generation(
    db: AsyncSession,
    *,
    document: Document,
    version: DocumentVersion,
    text: str,
    source_revision: int,
) -> bool:
    """Write one published source into its workspace's active generation, if it has one.

    Called by the worker after the legacy write and before it changes any source state;
    ``source_revision`` is the revision its commit will make current, and the item row commits with
    it. New points are written before the document's older points are pruned, so the document
    stays searchable throughout. A failure raises and the job is retried: a workspace in generation
    mode never publishes a source its active generation does not contain. Runs under the
    document's row lock (BGE-M3 embedding takes about a second per short document on CPU).
    """
    if None in (document.organization_id, document.workspace_id, document.knowledge_base_id):
        return False
    assignment = await db.get(WorkspaceRetrievalAssignment, document.workspace_id)
    if assignment is None or assignment.serving_mode != "generation":
        return False
    if not generations_enabled():
        raise RetrievalIndexUnavailableError("generation serving is not enabled in this deployment")
    generation = await db.get(IndexGeneration, assignment.active_generation_id)
    if generation is None or generation.workspace_id != document.workspace_id or generation.state != "ready":
        raise RetrievalIndexUnavailableError("active index generation is missing or not ready")
    contracts = generation_contracts(generation)
    write = ResolvedGenerationWriteIndex(
        scope=GenerationWriteScope(
            organization_id=document.organization_id,
            workspace_id=document.workspace_id,
            generation_id=UUID(generation.id),
        ),
        space=contracts.space,
        materialization=contracts.materialization,
        collection_name=contracts.collection_name,
    )
    chunks = chunk_text(text, contracts.materialization.chunk_size, contracts.materialization.chunk_overlap)
    vectors = await get_contract_embedder(contracts.candidate).embed_texts(chunks)
    adapter = get_generation_adapter()
    await adapter.upsert_document(
        write,
        vector_space=contracts.space,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        document_version=version.version,
        source_revision=source_revision,
        content_hash=version.content_hash,
        filename=document.filename,
        chunks=chunks,
        vectors=vectors,
    )
    await adapter.prune_document(write, document_id=document.id, keep_version=version.version, keep_chunks=len(chunks))
    item = await db.get(IndexGenerationItem, (generation.id, document.id))
    if item is None:
        item = IndexGenerationItem(generation_id=generation.id, document_id=document.id, attempts=0)
        db.add(item)
    item.source_revision, item.document_version, item.content_hash = source_revision, version.version, version.content_hash
    item.expected_chunk_count = item.indexed_chunk_count = len(chunks)
    item.attempts = (item.attempts or 0) + 1
    item.state, item.error_code = "complete", None
    return True


async def generation_lag(db: AsyncSession, generation: IndexGeneration, organization_id: int) -> dict:
    """Sources the generation does not match right now (ids only)."""
    sources = await eligible_sources(db, generation.workspace_id, organization_id)
    items = {
        item.document_id: item
        for item in (await db.scalars(select(IndexGenerationItem).where(IndexGenerationItem.generation_id == generation.id))).all()
    }
    missing = [
        document.id
        for document, version in sources
        if (item := items.get(document.id)) is None
        or item.state != "complete"
        or (item.source_revision, item.document_version, item.content_hash)
        != (document.source_revision, version.version, version.content_hash)
    ]
    eligible = {document.id for document, _ in sources}
    # Points of deleted or no longer eligible sources: never served (live_generation_hits drops
    # them), removed by the next build.
    stale = [document_id for document_id, item in items.items() if document_id not in eligible and item.state == "complete"]
    return {"missing_or_outdated": missing, "stale_points": stale}
