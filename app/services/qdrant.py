from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import get_settings


class QdrantService:
    collection_name = "rag_documents"

    def __init__(self, client: AsyncQdrantClient | None = None):
        if client is not None:
            self.client = client
            return

        raw_url = get_settings().qdrant_url

        # Defensive cleanup for accidental escaped URL values.
        url = (
            raw_url
            .replace("\\", "")
            .strip()
        )

        self.client = AsyncQdrantClient(
            url=url,
            timeout=30,
            trust_env=False,
        )

    async def ensure_collection(self, vector_size: int) -> None:
        collections = await self.client.get_collections()

        names = {item.name for item in collections.collections}

        if self.collection_name not in names:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

    @staticmethod
    def point_id(document_id: int, chunk_index: int) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"modai-stack:{document_id}:{chunk_index}",
            )
        )

    async def upsert_document(
        self,
        *,
        user_id: int,
        document_id: int,
        filename: str,
        organization_id: int | None = None,
        workspace_id: int | None = None,
        knowledge_base_id: int | None = None,
        document_version: int = 1,
        chunks: list[str],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk and vector counts must match")

        if not vectors:
            return

        await self.ensure_collection(len(vectors[0]))

        points = [
            models.PointStruct(
                id=self.point_id(document_id, index),
                vector=vector,
                payload={
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "workspace_id": workspace_id,
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document_id,
                    "document_version": document_version,
                    "filename": filename,
                    "chunk_index": index,
                    "text": chunk,
                },
            )
            for index, (chunk, vector) in enumerate(
                zip(chunks, vectors)
            )
        ]

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def _user_filter(
        self,
        user_id: int,
        organization_id: int | None = None,
        workspace_id: int | None = None,
        knowledge_base_id: int | None = None,
        document_id: int | None = None,
    ) -> models.Filter:
        conditions = [
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            )
        ]

        for key, value in (("organization_id", organization_id), ("workspace_id", workspace_id), ("knowledge_base_id", knowledge_base_id)):
            if value is not None:
                conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))

        if document_id is not None:
            conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=document_id),
                )
            )

        return models.Filter(must=conditions)

    async def search(
        self,
        *,
        user_id: int,
        vector: list[float],
        limit: int,
        organization_id: int | None = None,
        workspace_id: int | None = None,
        knowledge_base_id: int | None = None,
    ):
        return await self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit,
            query_filter=self._user_filter(user_id, organization_id, workspace_id, knowledge_base_id),
            with_payload=True,
        )

    async def delete_document_vectors(
        self,
        *,
        user_id: int,
        document_id: int,
    ) -> None:
        collections = await self.client.get_collections()

        names = {item.name for item in collections.collections}

        # Old PostgreSQL documents may exist without Qdrant vectors.
        if self.collection_name not in names:
            return

        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=self._user_filter(
                    user_id,
                    document_id,
                )
            ),
            wait=True,
        )

    async def health_check(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False


qdrant_service = QdrantService()
