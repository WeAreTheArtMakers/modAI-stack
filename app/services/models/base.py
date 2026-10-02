from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


class ModelProviderUnavailableError(RuntimeError):
    """Raised when a configured local model provider cannot be reached."""


class InvalidModelIdentifierError(ValueError):
    """Raised when a client passes an unsafe model identifier."""


@dataclass(frozen=True)
class ManagedModel:
    provider: str
    name: str
    size: int | None = None
    modified_at: str | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    capabilities: list[str] | None = None


@dataclass(frozen=True)
class ModelProviderStatus:
    provider: str
    endpoint: str
    ready: bool


class ModelProvider(ABC):
    name: str

    @abstractmethod
    async def health(self) -> ModelProviderStatus: ...

    @abstractmethod
    async def list_models(self) -> list[ManagedModel]: ...

    @abstractmethod
    async def get_model(self, model: str) -> ManagedModel | None: ...

    @abstractmethod
    async def pull_model(self, model: str) -> AsyncIterator[dict]: ...

    @abstractmethod
    async def delete_model(self, model: str) -> None: ...

    @abstractmethod
    async def get_running_models(self) -> list[str]: ...
