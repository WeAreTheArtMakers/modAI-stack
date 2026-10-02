import asyncio
import logging
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when the configured embedding model cannot be loaded safely."""


def embedding_model_unavailable_detail() -> str:
    return (
        "Embedding model unavailable. Run `python -m app.tools.prefetch_embedding_model` "
        "or configure EMBEDDING_MODEL with a provisioned local model directory."
    )


def _is_local_model_path(value: str) -> bool:
    expanded = Path(value).expanduser()
    return expanded.is_absolute() or value.startswith(("./", "../", "~"))


def embedding_model_status() -> dict:
    """Return safe, non-loading provisioning state for the configured embedding model."""
    settings = get_settings()
    model_name = settings.embedding_model
    is_local_path = _is_local_model_path(model_name)
    cache_dir = Path(settings.embedding_cache_dir).expanduser() if settings.embedding_cache_dir else None
    loaded = get_embedding_service()._model is not None
    if is_local_path:
        available = Path(model_name).expanduser().is_dir()
        display_name = f"local:{Path(model_name).expanduser().name}"
    else:
        cache_key = f"models--{model_name.replace('/', '--')}"
        available = (cache_dir / cache_key).is_dir() if cache_dir else None
        display_name = model_name
    return {
        "configured_model": display_name,
        "source": "local_path" if is_local_path else "huggingface_cache",
        "download_allowed": settings.embedding_allow_download,
        "cache_available": available,
        "ready": loaded or available is True,
        "status": "ready" if loaded else "available" if available is True else "unavailable" if available is False else "unverified",
    }


class EmbeddingService:
    """Lazy, process-local embedding model shared by all requests."""

    def __init__(self, model=None, *, allow_download: bool | None = None):
        self._model = model
        self._allow_download = allow_download

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            settings = get_settings()
            model_name = settings.embedding_model
            is_local_path = _is_local_model_path(model_name)
            local_path = Path(model_name).expanduser()
            if is_local_path and not local_path.is_dir():
                message = f"Configured local embedding model directory is unavailable: {local_path}"
                logger.error(message)
                raise EmbeddingModelUnavailableError(message)

            allow_download = (
                settings.embedding_allow_download
                if self._allow_download is None
                else self._allow_download
            )
            try:
                self._model = SentenceTransformer(
                    str(local_path) if is_local_path else model_name,
                    cache_folder=settings.embedding_cache_dir,
                    local_files_only=is_local_path or not allow_download,
                )
            except Exception as exc:
                if is_local_path:
                    message = f"Configured local embedding model directory could not be loaded: {local_path}"
                elif allow_download:
                    message = f"Configured embedding model could not be loaded: {model_name}"
                else:
                    message = (
                        f"Configured embedding model is not available in the local cache: {model_name}. "
                        "Run `python -m app.tools.prefetch_embedding_model` while connected "
                        "or configure a local model directory."
                    )
                logger.error(message, extra={"exception_type": type(exc).__name__})
                raise EmbeddingModelUnavailableError(message) from exc
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
