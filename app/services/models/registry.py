from functools import lru_cache

from app.services.models.base import ModelProvider
from app.services.models.ollama import OllamaModelProvider


@lru_cache
def get_model_provider(name: str) -> ModelProvider:
    if name == "ollama":
        return OllamaModelProvider()
    raise KeyError(name)


def configured_model_providers() -> list[ModelProvider]:
    return [get_model_provider("ollama")]
