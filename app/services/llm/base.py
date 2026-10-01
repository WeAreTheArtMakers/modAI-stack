from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str: ...
    @abstractmethod
    async def stream(self, prompt: str) -> AsyncIterator[str]: ...
    @abstractmethod
    async def health_check(self) -> bool: ...

