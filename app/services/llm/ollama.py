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

    async def stream(self, prompt: str) -> AsyncIterator[str]:
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
