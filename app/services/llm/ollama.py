import json
from collections.abc import AsyncIterator
import httpx
from app.core.config import get_settings
from app.services.llm.base import LLMProvider
class OllamaProvider(LLMProvider):
    def __init__(self, client: httpx.AsyncClient | None = None): self.client = client or httpx.AsyncClient(timeout=120)
    async def generate(self, prompt: str) -> str:
        r = await self.client.post(f"{get_settings().ollama_base_url}/api/generate", json={"model": get_settings().ollama_model, "prompt": prompt, "stream": False}); r.raise_for_status(); return r.json().get("response", "")
    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async with self.client.stream("POST", f"{get_settings().ollama_base_url}/api/generate", json={"model": get_settings().ollama_model, "prompt": prompt, "stream": True}) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line:
                    data = json.loads(line)
                    if data.get("response"): yield data["response"]
    async def health_check(self) -> bool:
        try: return (await self.client.get(f"{get_settings().ollama_base_url}/api/tags", timeout=5)).is_success
        except httpx.HTTPError: return False

