"""Staging-only retrieval from a validated index generation (design #27, reduced).

A workspace serves RAG from an index generation only when all of these hold:
- the deployment sets RETRIEVAL_GENERATIONS_ENABLED=true and APP_ENV=staging;
- its ``workspace_retrieval_assignments`` row says ``serving_mode='generation'``;
- the referenced generation belongs to that workspace, is ``ready`` (it passed
  ``app.tools.retrieval_generation validate``), and its stored contracts hash to their recorded
  SHA-256 values and match a reviewed registry candidate.

Workspaces without a row, or in ``legacy`` mode, keep the existing MiniLM ``rag_documents`` path
unchanged. A generation-mode workspace never falls back to the legacy collection: if anything above
fails, retrieval raises ``RetrievalIndexUnavailableError`` (HTTP 503 / WebSocket error).

Deliberately not implemented here (production prerequisites in the design): mirrored indexing of
new uploads into the active generation, outbox replay, the activation write gate, and admin APIs.
New or replaced documents in a generation-mode workspace are indexed by the worker into the legacy
collection only; their stale generation points are dropped at query time by the SQL check in
``live_generation_hits`` and the generation must be rebuilt to include them.
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
    WorkspaceRetrievalAssignment,
)
from app.services.rag.generation_qdrant import GenerationQdrantAdapter
from app.services.rag.retrieval_contract_registry import (
    ReviewedEmbeddingCandidate,
    get_reviewed_candidate,
)
from app.services.rag.retrieval_contracts import (
    AuthorizedTenantGeneration,
    EmbeddingSpaceContract,
    LegacyUnverifiedRetrieval,
    MaterializationContract,
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
    return get_settings().retrieval_generations_active


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
    """Keep hits whose document is still current in PostgreSQL: not deleted, in an authorized
    Knowledge Base, and at the same active version and source revision that was indexed."""
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
    """Documents a generation must contain: live, scoped, with a ready active version."""
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
