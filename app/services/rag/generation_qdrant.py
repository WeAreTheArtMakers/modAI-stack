"""Fail-closed Qdrant adapter for future generation-aware retrieval.

This module does not change the current legacy production serving path.
It does not activate a retrieval profile, create a generation automatically,
load BGE-M3, or modify workspace retrieval assignments.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import get_settings
from app.services.rag.retrieval_contracts import (
    EmbeddingSpaceContract,
    ResolvedGenerationWriteIndex,
    ResolvedRetrievalIndex,
    RetrievalCompatibilityError,
    collection_name_for_space,
    require_space_match,
    validate_vector,
)


GenerationIndex = (
    ResolvedRetrievalIndex
    | ResolvedGenerationWriteIndex
)


_DISTANCE_MAP = {
    "cosine": models.Distance.COSINE,
    "dot": models.Distance.DOT,
    "euclid": models.Distance.EUCLID,
}


_PAYLOAD_INDEXES = {
    "organization_id": models.PayloadSchemaType.INTEGER,
    "workspace_id": models.PayloadSchemaType.INTEGER,
    "knowledge_base_id": models.PayloadSchemaType.INTEGER,
    "document_id": models.PayloadSchemaType.INTEGER,
    "document_version": models.PayloadSchemaType.INTEGER,
    "source_revision": models.PayloadSchemaType.INTEGER,
    "index_generation_id": models.PayloadSchemaType.KEYWORD,
    "space_sha256": models.PayloadSchemaType.KEYWORD,
    "materialization_sha256": models.PayloadSchemaType.KEYWORD,
}


class GenerationQdrantAdapter:
    """Generation-scoped Qdrant operations.

    Callers cannot provide a raw collection name. All collection, tenant,
    generation and contract identity comes from immutable resolved objects.
    """

    # This is a safety ceiling, not an overfetch policy.
    # A later generation read path may choose a candidate window <= this cap.
    max_candidate_limit = 50

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
    ):
        if client is not None:
            self.client = client
            return

        url = (
            get_settings()
            .qdrant_url
            .replace("\\", "")
            .strip()
        )

        self.client = AsyncQdrantClient(
            url=url,
            timeout=30,
            trust_env=False,
        )

    @staticmethod
    def _distance(
        space: EmbeddingSpaceContract,
    ) -> models.Distance:
        try:
            return _DISTANCE_MAP[space.distance_metric]
        except KeyError as exc:
            raise RetrievalCompatibilityError(
                "unsupported Qdrant distance metric"
            ) from exc

    @staticmethod
    def _validate_positive(
        value: int,
        field_name: str,
    ) -> None:
        if value <= 0:
            raise RetrievalCompatibilityError(
                f"{field_name} must be positive"
            )

    @staticmethod
    def point_id(
        index: GenerationIndex,
        *,
        document_id: int,
        document_version: int,
        chunk_index: int,
    ) -> str:
        if document_id <= 0:
            raise RetrievalCompatibilityError(
                "document_id must be positive"
            )

        if document_version <= 0:
            raise RetrievalCompatibilityError(
                "document_version must be positive"
            )

        if chunk_index < 0:
            raise RetrievalCompatibilityError(
                "chunk_index must not be negative"
            )

        scope = index.scope

        identity = ":".join(
            (
                "modai-stack",
                "generation-point-v1",
                index.space.space_sha256,
                index.materialization.materialization_sha256,
                str(scope.generation_id),
                str(scope.workspace_id),
                str(document_id),
                str(document_version),
                str(chunk_index),
            )
        )

        return str(
            uuid5(
                NAMESPACE_URL,
                identity,
            )
        )

    @staticmethod
    def _base_filter(
        index: GenerationIndex,
        *,
        knowledge_base_ids: Sequence[int] | None = None,
        document_id: int | None = None,
        document_version: int | None = None,
    ) -> models.Filter:
        scope = index.scope

        conditions: list[models.FieldCondition] = [
            models.FieldCondition(
                key="organization_id",
                match=models.MatchValue(
                    value=scope.organization_id
                ),
            ),
            models.FieldCondition(
                key="workspace_id",
                match=models.MatchValue(
                    value=scope.workspace_id
                ),
            ),
            models.FieldCondition(
                key="index_generation_id",
                match=models.MatchValue(
                    value=str(scope.generation_id)
                ),
            ),
            models.FieldCondition(
                key="space_sha256",
                match=models.MatchValue(
                    value=index.space.space_sha256
                ),
            ),
            models.FieldCondition(
                key="materialization_sha256",
                match=models.MatchValue(
                    value=(
                        index.materialization
                        .materialization_sha256
                    )
                ),
            ),
        ]

        if knowledge_base_ids is not None:
            values = tuple(knowledge_base_ids)

            if (
                not values
                or any(value <= 0 for value in values)
            ):
                raise RetrievalCompatibilityError(
                    "knowledge base scope must contain positive IDs"
                )

            conditions.append(
                models.FieldCondition(
                    key="knowledge_base_id",
                    match=models.MatchAny(
                        any=list(values)
                    ),
                )
            )

        if document_id is not None:
            GenerationQdrantAdapter._validate_positive(
                document_id,
                "document_id",
            )
            conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(
                        value=document_id
                    ),
                )
            )

        if document_version is not None:
            GenerationQdrantAdapter._validate_positive(
                document_version,
                "document_version",
            )
            conditions.append(
                models.FieldCondition(
                    key="document_version",
                    match=models.MatchValue(
                        value=document_version
                    ),
                )
            )

        return models.Filter(must=conditions)

    @staticmethod
    def _validate_payload_schema_mapping(
        payload_schema: Mapping[str, object],
    ) -> list[str]:
        """Validate known indexes and return missing required fields.

        Extra payload indexes are allowed because one embedding-space
        collection may support multiple compatible materialization schemas.
        """

        if not isinstance(payload_schema, Mapping):
            raise RetrievalCompatibilityError(
                "Qdrant payload schema is invalid"
            )

        missing: list[str] = []

        for field_name, expected_type in _PAYLOAD_INDEXES.items():
            info = payload_schema.get(field_name)

            if info is None:
                missing.append(field_name)
                continue

            actual_type = getattr(
                info,
                "data_type",
                None,
            )

            if actual_type != expected_type:
                raise RetrievalCompatibilityError(
                    f"Qdrant payload index {field_name} type mismatch"
                )

        return missing

    async def validate_collection(
        self,
        index: GenerationIndex,
        *,
        require_payload_indexes: bool = False,
    ) -> None:
        expected_name = collection_name_for_space(
            index.space.space_sha256
        )

        if index.collection_name != expected_name:
            raise RetrievalCompatibilityError(
                "resolved collection identity mismatch"
            )

        info = await self.client.get_collection(
            index.collection_name
        )

        vectors = info.config.params.vectors

        if not isinstance(vectors, Mapping):
            raise RetrievalCompatibilityError(
                "generation collection must use named vectors"
            )

        if set(vectors) != {index.space.vector_name}:
            raise RetrievalCompatibilityError(
                "Qdrant vector-name contract mismatch"
            )

        params = vectors[index.space.vector_name]

        if params.size != index.space.dimensions:
            raise RetrievalCompatibilityError(
                "Qdrant vector dimension mismatch"
            )

        if (
            params.distance
            != self._distance(index.space)
        ):
            raise RetrievalCompatibilityError(
                "Qdrant distance metric mismatch"
            )

        if require_payload_indexes:
            missing = self._validate_payload_schema_mapping(
                getattr(
                    info,
                    "payload_schema",
                    {},
                )
            )

            if missing:
                raise RetrievalCompatibilityError(
                    "Qdrant required payload indexes are missing: "
                    + ", ".join(sorted(missing))
                )

    async def validate_payload_indexes(
        self,
        index: GenerationIndex,
    ) -> None:
        """Strict validation used by migration/pre-activation gates."""

        await self.validate_collection(
            index,
            require_payload_indexes=True,
        )

    async def _ensure_payload_indexes(
        self,
        index: ResolvedGenerationWriteIndex,
    ) -> None:
        """Repair only missing safe indexes.

        Existing indexes with an incompatible type fail closed before
        any missing index is created.
        """

        info = await self.client.get_collection(
            index.collection_name
        )

        missing = self._validate_payload_schema_mapping(
            getattr(
                info,
                "payload_schema",
                {},
            )
        )

        for field_name in missing:
            await self.client.create_payload_index(
                collection_name=index.collection_name,
                field_name=field_name,
                field_schema=_PAYLOAD_INDEXES[
                    field_name
                ],
                wait=True,
            )

    async def create_collection(
        self,
        index: ResolvedGenerationWriteIndex,
    ) -> bool:
        """Create or safely complete one verified space collection.

        Existing vector configuration is never mutated. Missing compatible
        payload indexes may be completed idempotently.
        """

        collections = await self.client.get_collections()
        names = {
            item.name
            for item in collections.collections
        }

        if index.collection_name in names:
            await self.validate_collection(index)
            await self._ensure_payload_indexes(index)
            return False

        await self.client.create_collection(
            collection_name=index.collection_name,
            vectors_config={
                index.space.vector_name:
                models.VectorParams(
                    size=index.space.dimensions,
                    distance=self._distance(
                        index.space
                    ),
                )
            },
        )

        await self._ensure_payload_indexes(index)

        return True

    @staticmethod
    def _validate_generation_payload(
        index: GenerationIndex,
        payload: Mapping[str, object],
    ) -> None:
        scope = index.scope

        expected = {
            "organization_id": scope.organization_id,
            "workspace_id": scope.workspace_id,
            "index_generation_id": str(
                scope.generation_id
            ),
            "space_sha256": (
                index.space.space_sha256
            ),
            "materialization_sha256": (
                index.materialization
                .materialization_sha256
            ),
            "payload_schema_version": (
                index.materialization
                .payload_schema_version
            ),
        }

        for key, value in expected.items():
            if payload.get(key) != value:
                raise RetrievalCompatibilityError(
                    f"Qdrant payload {key} mismatch"
                )

        for key in (
            "knowledge_base_id",
            "document_id",
            "document_version",
            "source_revision",
            "chunk_index",
        ):
            value = payload.get(key)

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                raise RetrievalCompatibilityError(
                    f"Qdrant payload {key} is invalid"
                )

        if payload["knowledge_base_id"] <= 0:
            raise RetrievalCompatibilityError(
                "Qdrant payload knowledge_base_id is invalid"
            )

        if payload["document_id"] <= 0:
            raise RetrievalCompatibilityError(
                "Qdrant payload document_id is invalid"
            )

        if payload["document_version"] <= 0:
            raise RetrievalCompatibilityError(
                "Qdrant payload document_version is invalid"
            )

        if payload["source_revision"] <= 0:
            raise RetrievalCompatibilityError(
                "Qdrant payload source_revision is invalid"
            )

        if payload["chunk_index"] < 0:
            raise RetrievalCompatibilityError(
                "Qdrant payload chunk_index is invalid"
            )

        if not isinstance(
            payload.get("content_hash"),
            str,
        ) or not payload["content_hash"]:
            raise RetrievalCompatibilityError(
                "Qdrant payload content_hash is invalid"
            )

    @classmethod
    def _validate_read_payload(
        cls,
        index: ResolvedRetrievalIndex,
        payload: Mapping[str, object],
    ) -> None:
        cls._validate_generation_payload(
            index,
            payload,
        )

        if (
            payload["knowledge_base_id"]
            not in index.scope.knowledge_base_ids
        ):
            raise RetrievalCompatibilityError(
                "Qdrant payload knowledge base is outside authorized scope"
            )

    async def search(
        self,
        index: ResolvedRetrievalIndex,
        *,
        query_space: EmbeddingSpaceContract,
        vector: Sequence[float],
        limit: int,
        candidate_limit: int | None = None,
    ):
        """Search one exact authorized generation.

        candidate_limit is intentionally explicit. This adapter enforces
        a hard bound but does not define the later product overfetch policy.
        """

        require_space_match(
            index.space,
            query_space,
        )
        validate_vector(
            vector,
            index.space,
        )

        if (
            limit <= 0
            or limit > self.max_candidate_limit
        ):
            raise RetrievalCompatibilityError(
                "search limit is outside the allowed range"
            )

        effective_limit = (
            limit
            if candidate_limit is None
            else candidate_limit
        )

        if (
            effective_limit < limit
            or effective_limit
            > self.max_candidate_limit
        ):
            raise RetrievalCompatibilityError(
                "candidate limit is outside the allowed range"
            )

        await self.validate_collection(index)

        query_filter = self._base_filter(
            index,
            knowledge_base_ids=(
                index.scope.knowledge_base_ids
            ),
        )

        hits = await self.client.search(
            collection_name=index.collection_name,
            query_vector=models.NamedVector(
                name=index.space.vector_name,
                vector=list(vector),
            ),
            query_filter=query_filter,
            limit=effective_limit,
            with_payload=True,
        )

        for hit in hits:
            payload = hit.payload

            if not isinstance(payload, Mapping):
                raise RetrievalCompatibilityError(
                    "Qdrant result payload is missing"
                )

            self._validate_read_payload(
                index,
                payload,
            )

        return hits

    async def upsert_document(
        self,
        index: ResolvedGenerationWriteIndex,
        *,
        vector_space: EmbeddingSpaceContract,
        knowledge_base_id: int,
        document_id: int,
        document_version: int,
        source_revision: int,
        content_hash: str,
        filename: str,
        chunks: Sequence[str],
        vectors: Sequence[Sequence[float]],
    ) -> list[str]:
        require_space_match(
            index.space,
            vector_space,
        )

        self._validate_positive(
            knowledge_base_id,
            "knowledge_base_id",
        )
        self._validate_positive(
            document_id,
            "document_id",
        )
        self._validate_positive(
            document_version,
            "document_version",
        )
        self._validate_positive(
            source_revision,
            "source_revision",
        )

        if not content_hash:
            raise RetrievalCompatibilityError(
                "content_hash must be non-empty"
            )

        if len(chunks) != len(vectors):
            raise RetrievalCompatibilityError(
                "chunk and vector counts must match"
            )

        for vector in vectors:
            validate_vector(
                vector,
                index.space,
            )

        if not vectors:
            return []

        await self.validate_collection(index)

        point_ids: list[str] = []
        points: list[models.PointStruct] = []

        for chunk_index, (
            chunk,
            vector,
        ) in enumerate(zip(chunks, vectors)):
            point_id = self.point_id(
                index,
                document_id=document_id,
                document_version=document_version,
                chunk_index=chunk_index,
            )

            point_ids.append(point_id)

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        index.space.vector_name:
                        list(vector)
                    },
                    payload={
                        "organization_id": (
                            index.scope.organization_id
                        ),
                        "workspace_id": (
                            index.scope.workspace_id
                        ),
                        "knowledge_base_id": (
                            knowledge_base_id
                        ),
                        "document_id": document_id,
                        "document_version": (
                            document_version
                        ),
                        "source_revision": (
                            source_revision
                        ),
                        "chunk_index": chunk_index,
                        "index_generation_id": str(
                            index.scope.generation_id
                        ),
                        "space_sha256": (
                            index.space.space_sha256
                        ),
                        "materialization_sha256": (
                            index.materialization
                            .materialization_sha256
                        ),
                        "payload_schema_version": (
                            index.materialization
                            .payload_schema_version
                        ),
                        "content_hash": content_hash,
                        "filename": filename,
                        "text": chunk,
                    },
                )
            )

        await self.client.upsert(
            collection_name=index.collection_name,
            points=points,
            wait=True,
        )

        return point_ids

    async def delete_document(
        self,
        index: ResolvedGenerationWriteIndex,
        *,
        document_id: int,
        document_version: int | None = None,
    ) -> None:
        await self.validate_collection(index)

        query_filter = self._base_filter(
            index,
            document_id=document_id,
            document_version=document_version,
        )

        await self.client.delete(
            collection_name=index.collection_name,
            points_selector=models.FilterSelector(
                filter=query_filter
            ),
            wait=True,
        )

    async def prune_document(
        self,
        index: ResolvedGenerationWriteIndex,
        *,
        document_id: int,
        keep_version: int,
        keep_chunks: int,
    ) -> None:
        """Delete this document's points except chunks 0..keep_chunks-1 of keep_version.

        Used after a new materialization is written, so the document never has no points.
        """
        self._validate_positive(keep_version, "keep_version")

        if keep_chunks < 0:
            raise RetrievalCompatibilityError(
                "keep_chunks must not be negative"
            )

        await self.validate_collection(index)

        scope = self._base_filter(
            index,
            document_id=document_id,
        )

        await self.client.delete(
            collection_name=index.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=scope.must,
                    should=[
                        models.Filter(
                            must_not=[
                                models.FieldCondition(
                                    key="document_version",
                                    match=models.MatchValue(
                                        value=keep_version
                                    ),
                                )
                            ]
                        ),
                        models.FieldCondition(
                            key="chunk_index",
                            range=models.Range(gte=keep_chunks),
                        ),
                    ],
                )
            ),
            wait=True,
        )

    async def count_generation(
        self,
        index: ResolvedGenerationWriteIndex,
    ) -> int:
        await self.validate_collection(index)

        result = await self.client.count(
            collection_name=index.collection_name,
            count_filter=self._base_filter(index),
            exact=True,
        )

        return int(result.count)

    async def scroll_generation(
        self,
        index: ResolvedGenerationWriteIndex,
        *,
        limit: int = 100,
        offset: int | str | None = None,
    ):
        if limit <= 0 or limit > 100:
            raise RetrievalCompatibilityError(
                "scroll limit is outside the allowed range"
            )

        await self.validate_collection(index)

        records, next_offset = await self.client.scroll(
            collection_name=index.collection_name,
            scroll_filter=self._base_filter(index),
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for record in records:
            payload = record.payload

            if not isinstance(payload, Mapping):
                raise RetrievalCompatibilityError(
                    "Qdrant record payload is missing"
                )

            self._validate_generation_payload(
                index,
                payload,
            )

        return records, next_offset
