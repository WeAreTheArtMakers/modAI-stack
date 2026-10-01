import asyncio
from collections.abc import Sequence
from functools import lru_cache

from app.core.config import get_settings


class EmbeddingService:
    """Lazy, process-local embedding model shared by all requests."""

    def __init__(self, model=None):
        self._model = model

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(get_settings().embedding_model)
        return self._model

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._get_model().encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True
        )
        return vectors.tolist()

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, texts)

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
