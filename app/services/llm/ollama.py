import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.services.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=180.0,
                write=30.0,
                pool=10.0,
            ),
            trust_env=False,
        )

    async def generate(self, prompt: str) -> str:
        settings = get_settings()

        response = await self.client.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
        )

        response.raise_for_status()

        data = response.json()
        return data.get("response", "")

    async def preload(self) -> None:
        """Load the configured model into memory without generating (Ollama's empty-prompt load).

        Ollama's own keep-alive policy is unchanged; this only avoids paying the model load inside
        the next user request.
        """
        settings = get_settings()
        response = await self.client.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={"model": settings.ollama_model, "prompt": "", "stream": False},
        )
        response.raise_for_status()

    async def stream(self, prompt: str, stats: dict | None = None) -> AsyncIterator[str]:
        """Stream tokens; when `stats` is given, fill it with Ollama's final timing counters."""
        settings = get_settings()

        async with self.client.stream(
            "POST",
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                data = json.loads(line)

                chunk = data.get("response")
                if chunk:
                    yield chunk

                if data.get("done") and stats is not None:
                    for key in ("load_duration", "prompt_eval_duration", "eval_duration", "total_duration"):
                        if isinstance(data.get(key), int):
                            stats[key.replace("_duration", "_ms")] = round(data[key] / 1e6, 1)
                    for key in ("prompt_eval_count", "eval_count"):
                        if isinstance(data.get(key), int):
                            stats[key] = data[key]

    async def health_check(self) -> bool:
        settings = get_settings()

        try:
            response = await self.client.get(
                f"{settings.ollama_base_url.rstrip('/')}/api/tags",
                timeout=5.0,
            )
            return response.is_success

        except httpx.HTTPError:
            return False
