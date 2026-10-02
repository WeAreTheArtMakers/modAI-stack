"""Download or verify the configured embedding model before starting workers."""

import asyncio
import sys

from app.core.config import get_settings
from app.services.rag.embeddings import EmbeddingModelUnavailableError, EmbeddingService


async def main() -> int:
    settings = get_settings()
    try:
        vector = await EmbeddingService(allow_download=True).embed_text("modAI embedding model verification")
    except EmbeddingModelUnavailableError as exc:
        print(f"Embedding model verification failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Embedding model ready: {settings.embedding_model} "
        f"({len(vector)} dimensions)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
