import json
import re
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.services.models.base import (
    InvalidModelIdentifierError,
    ManagedModel,
    ModelProvider,
    ModelProviderStatus,
    ModelProviderUnavailableError,
)

MODEL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$")


def validate_model_identifier(model: str) -> str:
    value = model.strip()
    if not value or len(value) > 200 or ".." in value or not MODEL_IDENTIFIER.fullmatch(value):
        raise InvalidModelIdentifierError("Invalid model identifier")
    return value


def _context_length(data: dict) -> int | None:
    model_info = data.get("model_info") or {}
    for key, value in model_info.items():
        if key.endswith(".context_length") and isinstance(value, int):
            return value
    return None


def _managed_model(data: dict, *, details: dict | None = None) -> ManagedModel:
    details = details or data.get("details") or {}
    return ManagedModel(
        provider="ollama",
        name=str(data.get("name") or data.get("model") or ""),
        size=data.get("size") if isinstance(data.get("size"), int) else None,
        modified_at=data.get("modified_at") if isinstance(data.get("modified_at"), str) else None,
        family=details.get("family") if isinstance(details.get("family"), str) else None,
        parameter_size=details.get("parameter_size") if isinstance(details.get("parameter_size"), str) else None,
        quantization=details.get("quantization_level") if isinstance(details.get("quantization_level"), str) else None,
        context_length=_context_length(data),
        capabilities=[item for item in data.get("capabilities", []) if isinstance(item, str)] or None,
    )


class OllamaModelProvider(ModelProvider):
    name = "ollama"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
            trust_env=False,
        )

    @property
    def endpoint(self) -> str:
        return get_settings().ollama_base_url.rstrip("/")

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.request(method, f"{self.endpoint}{path}", **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as exc:
            raise ModelProviderUnavailableError("Ollama provider is unavailable") from exc

    async def health(self) -> ModelProviderStatus:
        try:
            await self._request("GET", "/api/tags", timeout=5.0)
            ready = True
        except (ModelProviderUnavailableError, httpx.HTTPStatusError):
            ready = False
        return ModelProviderStatus(provider=self.name, endpoint=self.endpoint, ready=ready)

    async def list_models(self) -> list[ManagedModel]:
        response = await self._request("GET", "/api/tags")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ModelProviderUnavailableError("Ollama provider returned invalid data") from exc
        models = data.get("models", []) if isinstance(data, dict) else []
        return [_managed_model(item) for item in models if isinstance(item, dict)]

    async def get_model(self, model: str) -> ManagedModel | None:
        model = validate_model_identifier(model)
        try:
            response = await self._request("POST", "/api/show", json={"name": model})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ModelProviderUnavailableError("Ollama provider returned invalid data") from exc
        if not isinstance(data, dict):
            return None
        return _managed_model({"name": model, **data}, details=data.get("details") if isinstance(data.get("details"), dict) else None)

    async def pull_model(self, model: str) -> AsyncIterator[dict]:
        model = validate_model_identifier(model)
        try:
            async with self.client.stream(
                "POST",
                f"{self.endpoint}/api/pull",
                json={"name": model, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ModelProviderUnavailableError("Ollama model pull returned invalid data") from exc
                    if isinstance(data, dict):
                        yield {
                            "status": str(data.get("status", "working")),
                            "completed": data.get("completed") if isinstance(data.get("completed"), int) else None,
                            "total": data.get("total") if isinstance(data.get("total"), int) else None,
                        }
        except httpx.HTTPError as exc:
            raise ModelProviderUnavailableError("Ollama model pull failed") from exc

    async def delete_model(self, model: str) -> None:
        model = validate_model_identifier(model)
        await self._request("DELETE", "/api/delete", json={"name": model})

    async def get_running_models(self) -> list[str]:
        response = await self._request("GET", "/api/ps")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ModelProviderUnavailableError("Ollama provider returned invalid data") from exc
        models = data.get("models", []) if isinstance(data, dict) else []
        return [str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")]
