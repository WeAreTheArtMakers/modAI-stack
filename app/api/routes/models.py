import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user, require_admin
from app.core.config import get_settings
from app.models.schemas import (
    EmbeddingModelStatus,
    GenerationModelStatus,
    ManagedModelResponse,
    ModelProviderResponse,
    ModelSystemStatus,
)
from app.services.models.base import InvalidModelIdentifierError, ModelProviderStatus, ModelProviderUnavailableError
from app.services.models.registry import configured_model_providers, get_model_provider
from app.services.rag.embeddings import embedding_model_status

router = APIRouter(prefix="/models", tags=["models"])


def _provider_or_404(name: str):
    try:
        return get_model_provider(name)
    except KeyError as exc:
        raise HTTPException(404, "Unknown model provider") from exc


def _provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidModelIdentifierError):
        return HTTPException(422, "Invalid model identifier")
    return HTTPException(503, "Model provider is unavailable")


@router.get("/providers", response_model=list[ModelProviderResponse])
async def list_providers(user=Depends(current_user)):
    del user
    return await asyncio.gather(*(provider.health() for provider in configured_model_providers()))


@router.get("/status", response_model=ModelSystemStatus)
async def model_status(user=Depends(current_user)):
    del user
    provider = get_model_provider("ollama")
    provider_status = await provider.health()
    running: list[str] = []
    if provider_status.ready:
        try:
            running = await provider.get_running_models()
        except (ModelProviderUnavailableError, httpx.HTTPError):
            provider_status = ModelProviderStatus(provider="ollama", endpoint=provider_status.endpoint, ready=False)
    configured_model = get_settings().ollama_model
    return ModelSystemStatus(
        providers=[provider_status],
        generation=GenerationModelStatus(
            provider="ollama",
            configured_model=configured_model,
            ready=provider_status.ready,
            running=configured_model in running,
        ),
        embedding=EmbeddingModelStatus(**embedding_model_status()),
    )


@router.get("", response_model=list[ManagedModelResponse])
async def list_models(provider: str = "ollama", user=Depends(current_user)):
    del user
    try:
        return await _provider_or_404(provider).list_models()
    except (InvalidModelIdentifierError, ModelProviderUnavailableError, httpx.HTTPError) as exc:
        raise _provider_error(exc) from exc


@router.get("/{provider}/{model:path}", response_model=ManagedModelResponse)
async def get_model(provider: str, model: str, user=Depends(current_user)):
    del user
    try:
        result = await _provider_or_404(provider).get_model(model)
    except (InvalidModelIdentifierError, ModelProviderUnavailableError, httpx.HTTPError) as exc:
        raise _provider_error(exc) from exc
    if result is None:
        raise HTTPException(404, "Model not found")
    return result


@router.delete("/{provider}/{model:path}", status_code=204)
async def delete_model(provider: str, model: str, user=Depends(require_admin)):
    del user
    if provider == "ollama" and model == get_settings().ollama_model:
        raise HTTPException(409, "Configured generation model cannot be deleted")
    try:
        await _provider_or_404(provider).delete_model(model)
    except (InvalidModelIdentifierError, ModelProviderUnavailableError, httpx.HTTPError) as exc:
        raise _provider_error(exc) from exc
